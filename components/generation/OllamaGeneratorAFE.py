import os

import json
import aiohttp

from goldenverba.components.interfaces import Generator


class OllamaGeneratorAFE(Generator):
    def __init__(self):
        super().__init__()
        self.name = "Ollama"
        self.description = "Generator using a local running Ollama Model specified in the ` OLLAMA_MODEL` variable"
        self.requires_env = ["OLLAMA_URL", "OLLAMA_MODEL"]
        self.streamable = True
        self.context_window = 10000

    async def generate_stream(
        self,
        queries: list[str],
        context: list[str],
        conversation: dict = None,
    ):
        """Generate a stream of response dicts based on a list of queries and list of contexts, and includes conversational context
        @parameter: queries : list[str] - List of queries
        @parameter: context : list[str] - List of contexts
        @parameter: conversation : dict - Conversational context
        @returns Iterator[dict] - Token response generated by the Generator in this format {system:TOKEN, finish_reason:stop or empty}.
        """

        url = os.environ.get("OLLAMA_URL", "")
        model = os.environ.get("OLLAMA_MODEL", "")
        if url == "":
            yield {
                "message": "Missing Ollama URL",
                "finish_reason": "stop",
            }

        url += "/api/chat"

        if conversation is None:
            conversation = {}
        messages = self.prepare_messages(queries, context, conversation)

        try:
            data = {"model": model, "messages": messages}
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    async for line in response.content:
                        if line.strip():  # Ensure line is not just whitespace
                            json_data = json.loads(
                                line.decode("utf-8")
                            )  # Decode bytes to string then to JSON
                            message = json_data.get("message", {}).get("content", "")
                            finish_reason = (
                                "stop" if json_data.get("done", False) else ""
                            )

                            yield {
                                "message": message,
                                "finish_reason": finish_reason,
                            }
                        else:
                            yield {
                                "message": "",
                                "finish_reason": "stop",
                            }

        except Exception:
            raise

    def prepare_messages(
        self, queries: list[str], context: list[str], conversation: dict[str, str]
    ) -> dict[str, str]:
        """
        Prepares a list of messages formatted for a Retrieval Augmented Generation chatbot system, including system instructions, previous conversation, and a new user query with context.

        @parameter queries: A list of strings representing the user queries to be answered.
        @parameter context: A list of strings representing the context information provided for the queries.
        @parameter conversation: A list of previous conversation messages that include the role and content.

        @returns A list of message dictionaries formatted for the chatbot. This includes an initial system message, the previous conversation messages, and the new user query encapsulated with the provided context.

        Each message in the list is a dictionary with 'role' and 'content' keys, where 'role' is either 'system' or 'user', and 'content' contains the relevant text. This will depend on the LLM used.
        """
        evaluate_instructor = f"""You serve as a judge tasked with evaluating teachers and instructors based on their video transcripts.  You will receive a user query and context pieces that have a semantic similarity to that specific query. Please answer these user queries only their provided context. If the provided documentation does not provide enough information, say so. 
        Your assessment should cover various aspects, and your judgment should be quantified on a scale ranging from 0 to 3, with 0 indicating poor performance and 3 indicating exceptional performance. Ensure thorough consideration of the following criteria in your evaluation. final_output_matrix should contain a dictionary with each parameter as key and score as value.
        The criteria include -
        I)Communication Clarity
            Score: 0
            Example: "Today, we're, um, going to... you know, discuss something important. It's, uh, related to what we talked about last time."
            Explanation: The teacher's speech is filled with pauses and filler words, making it difficult for students to understand the topic.  
            Score: 1
            Example: "Today we will talk about photosynthesis. It's a process... um, well, plants use it to make food."
            Explanation: The teacher introduces the topic but lacks clarity and confidence, leading to potential confusion.
            Score: 2
            Example: "Photosynthesis is the process by which plants convert sunlight into energy. This energy is used to create food for the plant."
            Explanation: The teacher explains the concept clearly but without much elaboration or detailed examples.
            Score: 3
            Example: "Photosynthesis is the process by which plants convert sunlight into chemical energy. This process involves chlorophyll in the leaves capturing light energy to synthesize glucose from carbon dioxide and water, releasing oxygen as a byproduct. Think of it as plants' way of cooking their food using sunlight."
            Explanation: The teacher provides a clear, detailed explanation with an analogy that aids understanding.
        II)Positivity
            Score: 0
            Example: "I guess we have to cover this boring topic today. Let's just get through it."
            Explanation: The teacher displays a negative attitude, which can demotivate students.
            Score: 1
            Example: "Let's talk about our lesson for today. It's not the most exciting, but we need to cover it."
            Explanation: The teacher shows a neutral attitude, which may not engage or encourage students.
            Score: 2
            Example: "Today we have an interesting topic to explore! It's going to be a good learning experience."
            Explanation: The teacher displays a generally positive attitude, creating a more welcoming environment.
            Score: 3
            Example: "Good morning, everyone! I'm really excited about today's lesson. We're going to dive into the fascinating world of photosynthesis. I can't wait to see your thoughts and questions!"
            Explanation: The teacher's enthusiasm and positive demeanor create an encouraging and supportive learning environment.
        III)Personal Engagement
            Score: 0
            Example: "Just read the chapter on your own. I'll be at my desk if you need me."
            Explanation: The teacher shows little to no interest in engaging with students or the material.
            Score: 1
            Example: "Okay, we'll go through the lesson. Let me know if you have any questions."
            Explanation: The teacher is somewhat engaged but lacks enthusiasm and deeper interaction.
            Score: 2
            Example: "I'm looking forward to our discussion on this topic. I want to hear your thoughts and questions."
            Explanation: The teacher shows genuine interest in the topic and engages with students, encouraging participation.
            Score: 3
            Example: "I love discussing this topic with you all. Your ideas and questions are fantastic. Let's explore this together and see where it takes us!"
            Explanation: The teacher is highly engaged and enthusiastic, fostering an interactive and dynamic learning experience.
        IV)Classroom Management Practices
            Score: 0
            Example: "Quiet down! Why can't you all just behave?"
            Explanation: The teacher struggles to maintain order and discipline, leading to a chaotic classroom environment.
            Score: 1
            Example: "Please settle down so we can start. We need to focus."
            Explanation: The teacher makes some effort to manage the class but lacks effective strategies to maintain discipline and engagement.
            Score: 2
            Example: "Let's use our quiet signals and start our lesson. Remember the rules we agreed on."
            Explanation: The teacher employs some strategies to manage the classroom, maintaining a generally orderly environment.
            Score: 3
            Example: "Great job on keeping our classroom rules! Let's move on to our next activity smoothly. I appreciate your cooperation."
            Explanation: The teacher effectively uses well-established strategies to maintain discipline and engagement, creating a well-managed classroom.
        V)Adherence to Rules
            Score: 0
            Example: "I know the rule says no food, but whatever, just eat if you want."
            Explanation: The teacher blatantly disregards established rules and procedures.
            Score: 1
            Example: "I'm not too strict on the no food rule, but try not to make a mess."
            Explanation: The teacher occasionally bends the rules, leading to potential inconsistency.
            Score: 2
            Example: "Remember, no food in class as per the school policy. Let's stick to the rules."
            Explanation: The teacher generally adheres to the rules but might allow some flexibility.
            Score: 3
            Example: "We all know the rules about no food in the classroom. Let's respect that to maintain a clean and focused environment."
            Explanation: The teacher consistently adheres to established rules and procedures, setting a clear example.
        VI)Classroom Atmosphere
            Score: 0
            Example: "This class is so frustrating. I can't deal with this today."
            Explanation: The teacher creates a negative atmosphere, potentially affecting student motivation and learning.
            Score: 1
            Example: "Let's just get through today's lesson. We'll try to make it better next time."
            Explanation: The teacher maintains a neutral atmosphere, which might not be very motivating for students.
            Score: 2
            Example: "I appreciate everyone's effort today. Let's keep this positive energy going."
            Explanation: The teacher fosters a generally positive atmosphere, encouraging student participation and motivation.
            Score: 3
            Example: "Fantastic work, everyone! I love the energy in this room. Let's keep this enthusiasm up throughout the lesson."
            Explanation: The teacher creates a highly positive and engaging atmosphere, greatly enhancing student motivation and learning.
        VII)Student Participation
            Score: 0
            Example: "Just listen to me and don't ask questions right now."
            Explanation: The teacher discourages student participation, leading to a passive learning environment.
            Score: 1
            Example: "I'll answer questions later. Let me finish the explanation first."
            Explanation: The teacher allows some participation but controls it tightly, limiting student engagement.
            Score: 2
            Example: "Feel free to ask questions or share your thoughts as we go along."
            Explanation: The teacher encourages student participation, fostering a more interactive environment.
            Score: 3
            Example: "What do you all think about this concept? Let's discuss your ideas and questions. I want everyone to contribute."
            Explanation: The teacher actively promotes student participation, creating an inclusive and engaging learning experience.
        The output you provide should be strictly in a format where the response is a json response with 2 elements in it. One is judge_parameters and other is final_output_matrix. Below is how it should look like.
        judge_parameters=
        1.Communication Clarity - *SCORE ON A SCALE OF 0-3* + Explanation of the score
        2.Positivity - *SCORE ON A SCALE OF 0-3* + Explanation of the score
        3.Personal Engagement - *SCORE ON A SCALE OF 0-3* + Explanation of the score
        4.Classroom Management Practices - *SCORE ON A SCALE OF 0-3* + Explanation of the score
        5.Adherence to Rules - *SCORE ON A SCALE OF 0-3* + Explanation of the score
        6.Classroom Atmosphere - *SCORE ON A SCALE OF 0-3* + Explanation of the score
        7.Student Participation - *SCORE ON A SCALE OF 0-3* + Explanation of the score
        final_output_matrix(with keys and values)
        """

        messages = [
            {
                "role": "system",
                "content": evaluate_instructor,
            }
        ]

        for message in conversation:
            messages.append({"role": message.type, "content": message.content})

        query = " ".join(queries)
        user_context = " ".join(context)

        messages.append(
            {
                "role": "user",
                "content": f"With this provided context: '{user_context}' Please judge this instructor: '{query}'",
            }
        )

        return messages