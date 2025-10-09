import os

from openai import OpenAI

# api_key = os.environ["API_KEY"]
api_key = ""
url = "https://foundation-models.api.cloud.ru/v1"

client = OpenAI(
   api_key=api_key,
   base_url=url
)

# response = client.chat.completions.create(
#    model="deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
#    max_tokens=5000,
#    temperature=0.5,
#    presence_penalty=0,
#    top_p=0.95,
#    messages=[
#       {
#             "role": "user",
#             "content":"Как написать хороший код?"
#       }
#    ]
# )

# print(response.choices[0].message.content)

# Qwen/Qwen3-235B-A22B-Instruct-2507

response = client.embeddings.create(
    model="Qwen/Qwen3-Embedding-0.6B",
    input=["Как написать хороший код?"]
)

print(response.data[0].embedding)