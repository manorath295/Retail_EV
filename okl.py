from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_tavily import TavilySearch
import os, getpass
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel, Field
from typing_extensions import TypedDict
from typing import Literal, cast
from typing import Annotated
from dotenv import load_dotenv
from langgraph.types import Command, interrupt
from langgraph.checkpoint.memory import MemorySaver

import nest_asyncio
nest_asyncio.apply()
load_dotenv() 
print(f"Tavily Key: {os.environ.get('TAVILY_API_KEY')}")
print(f"Google Key: {os.environ.get('GOOGLE_API_KEY')}")
class ProductState(TypedDict):
       messages: Annotated[list, add_messages]
       tavily_search: dict
       next_node: str
class NodeSelectionResponseFormat(BaseModel):
   node_name: Literal['greetings_node', 'search_node'] = Field(
       description="Name of the node to be activated for further processing."
   )

tavily_search_tool = TavilySearch(
   max_results=5,
   include_answer=True,
   include_raw_content=True,
   time_range="year",
)

llm = ChatGoogleGenerativeAI(
   model = "gemini-2.0-flash",
   max_tokens = None,
   timeout = None,
   max_retries = 0,
)
NODE_IDENTIFIER_PROMPT = '''We have build a graph utilizing the LangGraph framework \
All the graph details are listed below. Based on the user's conversation history, \
you need yo identify the perfect node which is able to process the input and return the \
name of the node only in the response. Apart from the node name no need to return anything \
else in the response.

Node descriptions
- greetings_node: When a user starts the conversation, activate this node. This node will \
ask user to provide provide the product details he is looking for.
- search_node: when a user directly provide the details about the product he is looking \
for, you need to call the search node directly, no need to ask user for providing the \
name and product specification again.
'''

GREETINGS_NODE_PROMPT = '''You just need to ask the user to provide product details that a \
user is looking to search.
'''

PREPARE_SUMMARY_PROMPT = '''You will be provided with user's message for filtering products \
along with the couple of web pages details from search result. You need to prepare small description \
from the provided web page details for top 5-10 products combined from all the web page details.

Make sure that while preparing the description of a product, prioritize the users requirements \
and focus that along with other details.

Make sure the to highlight the unique properties of all the top products in the description \
for the user.

You should not mention that the product that you are providing is from the web search result or \
anything similar to that. Just say These are the top products that I found for you so \
something similar to that only.
'''
def node_identifier(state: ProductState):
       model = llm.with_structured_output(NodeSelectionResponseFormat, include_raw=True)
       system_message = SystemMessage(NODE_IDENTIFIER_PROMPT)
       conversations = [system_message] + [*state['messages']]
       response = cast(AIMessage, model.invoke(conversations))

       if response['parsed'].node_name == 'search_node':
           return {
               'next_node': response['parsed'].node_name,
           }

       return {'next_node': response['parsed'].node_name}
def greetings_node(state: ProductState):
       model = llm
       system_message = SystemMessage(GREETINGS_NODE_PROMPT)
       conversations = [system_message] + [*state['messages']]
       response = cast(AIMessage, model.invoke(conversations))
       res = {
           'messages': [response],
           'next_node': 'user_input_node'
       }
       return res
def user_input_node(state: ProductState):
       feedback = interrupt("Please provide feedback:")
       return {'next_node': 'search_node'}
def search_node(state: ProductState):
       search_query = state['messages'][-1].content
       search_result = tavily_search_tool.invoke({'query': search_query})

       row_content = ""
       for d in search_result['results']:
           row_content += "Page Content\n"
           row_content += f"URL: {d['url']}\n"
           row_content += f"Title: {d['title']}\n"
           row_content += f"Row Content: {d['raw_content']}\n"

       return {'tavily_search': row_content }
def prepare_summary_node(state: ProductState):
       model = llm
       system_message = SystemMessage(PREPARE_SUMMARY_PROMPT)
       conversations = [system_message] + [*state['messages']] + [HumanMessage(content=state['tavily_search'])]
       response = cast(AIMessage, model.invoke(conversations))
       return {'messages': [response]}
def call_next_node(state: ProductState) -> Literal['greetings_node', 'search_node']:
       return state['next_node']
graph = StateGraph(ProductState)

graph.add_node('node_identifier', node_identifier)
graph.add_node('greetings_node', greetings_node)
graph.add_node('user_input_node', user_input_node)
graph.add_node('search_node', search_node)
graph.add_node('prepare_summary_node', prepare_summary_node)

graph.add_edge(START, 'node_identifier')
graph.add_conditional_edges('node_identifier', call_next_node)
graph.add_edge('greetings_node', 'user_input_node')
graph.add_edge('user_input_node', 'search_node')
graph.add_edge('search_node', 'prepare_summary_node')

graph.set_finish_point('prepare_summary_node')
app = graph.compile(checkpointer=MemorySaver())
thread = {"configurable": {"thread_id": "1"}}

def stream_graph_updates(user_input: str):
   for event in app.stream({"messages": [HumanMessage(user_input)]}, thread, stream_mode="updates"):
       if '__interrupt__' not in event.keys():
           for value in event.values():
               if 'messages' in value.keys():
                   print(f"AI: {value['messages'][-1].content}")
                   print("------------------------------------------------")

while True:
   user_input = input("User: ")
   if user_input.lower() in ["quit", "exit", "q"]:
       print("Goodbye!")
       break
   stream_graph_updates(user_input)