
# File: main.py
# Description: An advanced multi-tool agent for ServiceNow.
# (MODIFIED: Swapped to a Llama 3.1 model that supports tool calling)

import uvicorn
import os
import requests
from dotenv import load_dotenv
from typing import Type, List, Optional
from pydantic import BaseModel, Field

from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

# --- LangChain Imports ---
from langchain_nvidia_ai_endpoints import ChatNVIDIA # Using NVIDIA's library
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferWindowMemory
from langchain_core.agents import AgentFinish

# --- 1. Load Environment Variables ---
load_dotenv()

# --- 2. Helper Functions ---
def get_servicenow_credentials():
    instance = os.getenv("SERVICENOW_INSTANCE")
    user = os.getenv("SERVICENOW_USERNAME")
    pwd = os.getenv("SERVICENOW_PASSWORD")
    if not all([instance, user, pwd]): return None, None, None
    return instance, user, pwd

def get_sys_id(instance, user, pwd, table, query_field, query_value):
    url = f"{instance}/api/now/table/{table}"
    params = {"sysparm_query": f"{query_field}={query_value}", "sysparm_limit": "1", "sysparm_fields": "sys_id"}
    headers = {"Accept": "application/json"}
    try:
        response = requests.get(url, auth=(user, pwd), headers=headers, params=params)
        response.raise_for_status()
        results = response.json().get("result", [])
        if results: return results[0]['sys_id']
    except Exception as e: print(f"Error getting sys_id: {e}")
    return None

# --- 3. ServiceNow Custom Tool Definitions ---
class GetIncidentInput(BaseModel):
    incident_number: str = Field(description="The full incident number, e.g., 'INC0010001'.")
class GetIncidentTool(BaseTool):
    name: str = "get_incident_details"
    description: str = "Use this tool to get details for a specific incident ticket."
    args_schema: Type[BaseModel] = GetIncidentInput
    def _run(self, incident_number: str):
        instance, user, pwd = get_servicenow_credentials()
        if not instance: return "ServiceNow credentials not configured."
        url = f"{instance}/api/now/table/incident"
        params = {"sysparm_query": f"number={incident_number}", "sysparm_limit": "1", "sysparm_fields": "number,short_description,description,state,assignment_group,caller_id"}
        headers = {"Accept": "application/json"}
        try:
            response = requests.get(url, auth=(user, pwd), headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            results = data.get("result", [])
            if not isinstance(results, list) or not results: return f"No incident found with the number {incident_number}."
            incident_data = results[0]
            if not isinstance(incident_data, dict): return f"No valid incident data found for {incident_number}."
            def get_display_value(data, key):
                field_data = data.get(key)
                if isinstance(field_data, dict): return field_data.get('display_value', 'N/A')
                return 'N/A'
            state_value = incident_data.get('state', 'N/A')
            assignment_group = get_display_value(incident_data, 'assignment_group')
            caller = get_display_value(incident_data, 'caller_id')
            formatted_result = (f"Incident Details for {incident_data.get('number', 'N/A')}:\n"
                                f"- Short Description: {incident_data.get('short_description', 'N/A')}\n"
                                f"- State: {state_value}\n"
                                f"- Assignment Group: {assignment_group}\n"
                                f"- Caller: {caller}\n"
                                f"- Full Description: {incident_data.get('description', 'N/A')}")
            return formatted_result
        except Exception as e: return f"An unexpected error occurred: {e}"
    def _arun(self, incident_number: str): raise NotImplementedError()

class SearchIncidentsInput(BaseModel):
    search_term: str = Field(description="Keyword or phrase to search for in incident short descriptions.")
class SearchIncidentsTool(BaseTool):
    name: str = "search_incidents"
    description: str = "Use this tool to search for incidents by a keyword. Returns a list of matching incidents."
    args_schema: Type[BaseModel] = SearchIncidentsInput
    def _run(self, search_term: str):
        instance, user, pwd = get_servicenow_credentials()
        if not instance: return "ServiceNow credentials not configured."
        url = f"{instance}/api/now/table/incident"
        params = {"sysparm_query": f"short_descriptionLIKE{search_term}", "sysparm_limit": "5", "sysparm_fields": "number,short_description"}
        headers = {"Accept": "application/json"}
        try:
            response = requests.get(url, auth=(user, pwd), headers=headers, params=params)
            response.raise_for_status()
            results = response.json().get("result", [])
            if not results: return f"No incidents found matching '{search_term}'."
            formatted_results = ["Found incidents:"]
            for item in results: formatted_results.append(f"- {item.get('number')}: {item.get('short_description')}")
            return "\n".join(formatted_results)
        except Exception as e: return f"An error occurred during search: {e}"
    def _arun(self, search_term: str): raise NotImplementedError()

class CreateIncidentInput(BaseModel):
    short_description: str = Field(description="A brief summary of the issue for the new incident.")
class CreateIncidentTool(BaseTool):
    name: str = "create_incident"
    description: str = "Use this tool to create a new incident ticket. Provide a short description of the problem."
    args_schema: Type[BaseModel] = CreateIncidentInput
    def _run(self, short_description: str):
        instance, user, pwd = get_servicenow_credentials()
        if not instance: return "ServiceNow credentials not configured."
        caller_sys_id = get_sys_id(instance, user, pwd, "sys_user", "name", "Abel Tuter")
        if not caller_sys_id: return "Could not find the default caller 'Abel Tuter' to create the incident."
        url = f"{instance}/api/now/table/incident"
        payload = {"short_description": short_description, "caller_id": caller_sys_id, "urgency": "3", "impact": "3"}
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        try:
            response = requests.post(url, auth=(user, pwd), headers=headers, json=payload)
            response.raise_for_status()
            new_incident_number = response.json().get("result", {}).get("number", "UNKNOWN")
            return f"Successfully created new incident: {new_incident_number}."
        except Exception as e: return f"An error occurred while creating the incident: {e}"
    def _arun(self, short_description: str): raise NotImplementedError()

class UpdateIncidentInput(BaseModel):
    incident_number: str = Field(description="The incident number to update, e.g., 'INC0010001'.")
    work_note: str = Field(description="The comment or work note to add to the incident.")
class UpdateIncidentTool(BaseTool):
    name: str = "update_incident"
    description: str = "Use this tool to add a work note or comment to an existing incident."
    args_schema: Type[BaseModel] = UpdateIncidentInput
    def _run(self, incident_number: str, work_note: str):
        instance, user, pwd = get_servicenow_credentials()
        if not instance: return "ServiceNow credentials not configured."
        incident_sys_id = get_sys_id(instance, user, pwd, "incident", "number", incident_number)
        if not incident_sys_id: return f"Could not find incident {incident_number} to update."
        url = f"{instance}/api/now/table/incident/{incident_sys_id}"
        payload = {"work_notes": work_note}
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        try:
            response = requests.patch(url, auth=(user, pwd), headers=headers, json=payload)
            response.raise_for_status()
            return f"Successfully added note to incident {incident_number}."
        except Exception as e: return f"An error occurred while updating the incident: {e}"
    def _arun(self, incident_number: str, work_note: str): raise NotImplementedError()

class ListOpenIncidentsForUserInput(BaseModel):
    user_name: str = Field(description="The full name of the user, e.g., 'Beth Anglin'.")
class ListOpenIncidentsForUserTool(BaseTool):
    name: str = "list_open_incidents_for_caller"
    description: str = "Use this tool to list all OPEN incidents reported by a specific user (caller)."
    args_schema: Type[BaseModel] = ListOpenIncidentsForUserInput
    def _run(self, user_name: str):
        instance, user, pwd = get_servicenow_credentials()
        if not instance: return "ServiceNow credentials not configured."
        caller_sys_id = get_sys_id(instance, user, pwd, "sys_user", "name", user_name)
        if not caller_sys_id: return f"Could not find a user named '{user_name}'."
        url = f"{instance}/api/now/table/incident"
        params = {"sysparm_query": f"caller_id={caller_sys_id}^active=true", "sysparm_limit": "10", "sysparm_fields": "number,short_description,state"}
        headers = {"Accept": "application/json"}
        try:
            response = requests.get(url, auth=(user, pwd), headers=headers, params=params)
            response.raise_for_status()
            results = response.json().get("result", [])
            if not results: return f"No open incidents found for {user_name}."
            formatted_results = [f"Open incidents for {user_name}:"]
            for item in results: formatted_results.append(f"- {item.get('number')}: {item.get('short_description')} (State: {item.get('state')})")
            return "\n".join(formatted_results)
        except Exception as e: return f"An error occurred: {e}"
    def _arun(self, user_name: str): raise NotImplementedError()

class ListIncidentsAssignedToUserInput(BaseModel):
    user_name: str = Field(description="The full name of the user, e.g., 'David Loo'.")
class ListIncidentsAssignedToUserTool(BaseTool):
    name: str = "list_incidents_assigned_to_user"
    description: str = "Use this tool to find all incidents (open or closed) assigned to a specific user."
    args_schema: Type[BaseModel] = ListIncidentsAssignedToUserInput
    def _run(self, user_name: str):
        instance, user, pwd = get_servicenow_credentials()
        if not instance: return "ServiceNow credentials not configured."
        assignee_sys_id = get_sys_id(instance, user, pwd, "sys_user", "name", user_name)
        if not assignee_sys_id: return f"Could not find a user named '{user_name}' to check assignments."
        url = f"{instance}/api/now/table/incident"
        params = {"sysparm_query": f"assigned_to={assignee_sys_id}", "sysparm_limit": "10", "sysparm_fields": "number,short_description,state"}
        headers = {"Accept": "application/json"}
        try:
            response = requests.get(url, auth=(user, pwd), headers=headers, params=params)
            response.raise_for_status()
            results = response.json().get("result", [])
            if not results: return f"No incidents are currently assigned to {user_name}."
            formatted_results = [f"Incidents assigned to {user_name}:"]
            for item in results: formatted_results.append(f"- {item.get('number')}: {item.get('short_description')} (State: {item.get('state')})")
            return "\n".join(formatted_results)
        except Exception as e: return f"An error occurred: {e}"
    def _arun(self, user_name: str): raise NotImplementedError()

class SearchKnowledgeBaseInput(BaseModel):
    search_term: str = Field(description="The topic or question to search for in the knowledge base.")
class SearchKnowledgeBaseTool(BaseTool):
    name: str = "search_knowledge_base"
    description: str = "Use this tool to search for helpful articles in the ServiceNow knowledge base."
    args_schema: Type[BaseModel] = SearchKnowledgeBaseInput
    def _run(self, search_term: str):
        instance, user, pwd = get_servicenow_credentials()
        if not instance: return "ServiceNow credentials not configured."
        url = f"{instance}/api/now/table/kb_knowledge"
        params = {"sysparm_query": f"short_descriptionLIKE{search_term}", "sysparm_limit": "3", "sysparm_fields": "number,short_description,article_body"}
        headers = {"Accept": "application/json"}
        try:
            response = requests.get(url, auth=(user, pwd), headers=headers, params=params)
            response.raise_for_status()
            results = response.json().get("result", [])
            if not results: return f"No knowledge base articles found matching '{search_term}'."
            formatted_results = ["Found knowledge base articles:"]
            for item in results:
                body = item.get('article_body', 'No content.')
                #clean_body = requests.utils.unquote(body).replace('</p>', '\n').replace('<p>', '').replace('<strong>', '').replace('</strong>', '')
                clean_body = body.replace('</p>', ' ').replace('<p>', ' ').replace('<strong>', '').replace('</strong>', '').strip()
                formatted_results.append(f"- {item.get('number')}: {item.get('short_description')}\n  Summary: {clean_body[:150]}...")
            return "\n".join(formatted_results)
        except Exception as e: return f"An error occurred while searching the knowledge base: {e}"
    def _arun(self, search_term: str): raise NotImplementedError()

class DeleteIncidentInput(BaseModel):
    incident_number: str = Field(description="The incident number to delete, e.g., 'INC0010001'.")

class DeleteIncidentTool(BaseTool):
    name: str = "delete_incident"
    description: str = "Use this tool to permanently delete an incident record. WARNING: This action cannot be undone."
    args_schema: Type[BaseModel] = DeleteIncidentInput
    def _run(self, incident_number: str):
        instance, user, pwd = get_servicenow_credentials()
        if not instance: return "ServiceNow credentials not configured."
        incident_sys_id = get_sys_id(instance, user, pwd, "incident", "number", incident_number)
        if not incident_sys_id: return f"Could not find incident {incident_number} to delete."
        url = f"{instance}/api/now/table/incident/{incident_sys_id}"
        headers = {"Accept": "application/json"}
        try:
            response = requests.delete(url, auth=(user, pwd), headers=headers)
            response.raise_for_status()
            # Explicitly return the success message here
            return f"Successfully deleted incident {incident_number}." 
        except requests.exceptions.HTTPError as err:
            if err.response.status_code == 404:
                return f"Could not find incident {incident_number} to delete."
            return f"An HTTP error occurred: {err}. Please check user permissions."
        except Exception as e:
            return f"An unexpected error occurred: {e}"
    def _arun(self, incident_number: str): raise NotImplementedError()

class ResolveIncidentInput(BaseModel):
    incident_number: str = Field(description="The incident number to resolve, e.g., 'INC0010001'.")
    resolution_note: str = Field(description="A brief description of the solution or resolution.")
class ResolveIncidentTool(BaseTool):
    name: str = "resolve_incident"
    description: str = "Use this tool to resolve and close an incident ticket. Requires a resolution note."
    args_schema: Type[BaseModel] = ResolveIncidentInput
    def _run(self, incident_number: str, resolution_note: str):
        instance, user, pwd = get_servicenow_credentials()
        if not instance: return "ServiceNow credentials not configured."
        incident_sys_id = get_sys_id(instance, user, pwd, "incident", "number", incident_number)
        if not incident_sys_id: return f"Could not find incident {incident_number} to resolve."
        url = f"{instance}/api/now/table/incident/{incident_sys_id}"
        payload = {"state": "6", "resolution_notes": resolution_note}  # '6' is the out-of-the-box value for 'Resolved' state
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        try:
            response = requests.patch(url, auth=(user, pwd), headers=headers, json=payload)
            response.raise_for_status()
            return f"Successfully resolved incident {incident_number} with the note: '{resolution_note}'."
        #except Exception as e: return f"An error occurred while resolving the incident: {e}"
        except requests.exceptions.HTTPError as err:
            return f"An HTTP error occurred while resolving the incident: {err}. Please check user permissions."
        except Exception as e:
            return f"An unexpected error occurred while resolving the incident: {e}"
    def _arun(self, incident_number: str, resolution_note: str): raise NotImplementedError()

class AssignIncidentInput(BaseModel):
    incident_number: str = Field(description="The incident number to assign, e.g., 'INC0010001'.")
    assign_to_user: Optional[str] = Field(description="The full name of the user to assign the incident to.")
    assign_to_group: Optional[str] = Field(description="The name of the group to assign the incident to.")
class AssignIncidentTool(BaseTool):
    name: str = "assign_incident"
    description: str = "Use this tool to assign an incident to a specific user or group. Provide either a user name or a group name, not both."
    args_schema: Type[BaseModel] = AssignIncidentInput
    def _run(self, incident_number: str, assign_to_user: Optional[str] = None, assign_to_group: Optional[str] = None):
        instance, user, pwd = get_servicenow_credentials()
        if not instance: return "ServiceNow credentials not configured."
        incident_sys_id = get_sys_id(instance, user, pwd, "incident", "number", incident_number)
        if not incident_sys_id: return f"Could not find incident {incident_number} to assign."
        url = f"{instance}/api/now/table/incident/{incident_sys_id}"
        payload = {}
        if assign_to_user and assign_to_group: return "Please provide either a user or a group to assign the incident, not both."
        if assign_to_user:
            assignee_sys_id = get_sys_id(instance, user, pwd, "sys_user", "name", assign_to_user)
            if not assignee_sys_id: return f"Could not find a user named '{assign_to_user}'."
            payload["assigned_to"] = assignee_sys_id
            note = f"Incident assigned to user {assign_to_user}."
        elif assign_to_group:
            group_sys_id = get_sys_id(instance, user, pwd, "sys_user_group", "name", assign_to_group)
            if not group_sys_id: return f"Could not find a group named '{assign_to_group}'."
            payload["assignment_group"] = group_sys_id
            note = f"Incident assigned to group {assign_to_group}."
        else: return "Please specify a user or a group to assign the incident to."
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        try:
            response = requests.patch(url, auth=(user, pwd), headers=headers, json=payload)
            response.raise_for_status()
            return f"Successfully assigned incident {incident_number}."
        #except Exception as e: return f"An error occurred while assigning the incident: {e}"
        except requests.exceptions.HTTPError as err:
            return f"An HTTP error occurred while assigning the incident: {err}. Please check user permissions."
        except Exception as e:
            return f"An unexpected error occurred while assigning the incident: {e}"
    def _arun(self, incident_number: str, assign_to_user: Optional[str] = None, assign_to_group: Optional[str] = None): raise NotImplementedError()

class GetIncidentMetricsInput(BaseModel):
    group_name: str = Field(description="The name of the assignment group to get metrics for, e.g., 'Software'.")
class GetIncidentMetricsTool(BaseTool):
    name: str = "get_incident_metrics"
    description: str = "Use this tool to get average resolution time for incidents assigned to a specific group."
    args_schema: Type[BaseModel] = GetIncidentMetricsInput
    def _run(self, group_name: str):
        instance, user, pwd = get_servicenow_credentials()
        if not instance: return "ServiceNow credentials not configured."
        group_sys_id = get_sys_id(instance, user, pwd, "sys_user_group", "name", group_name)
        if not group_sys_id: return f"Could not find an assignment group named '{group_name}'."
        url = f"{instance}/api/now/stats/incident"
        params = {"sysparm_query": f"assignment_group={group_sys_id}", "sysparm_count": "true", "sysparm_fields": "resolved_at", "sysparm_group_by": "assignment_group"}
        headers = {"Accept": "application/json"}
        try:
            response = requests.get(url, auth=(user, pwd), headers=headers, params=params)
            response.raise_for_status()
            results = response.json().get("result", [])
            if not results: return f"No metrics found for group '{group_name}'."
            resolved_incidents = [item for item in results if item.get('resolved_at')]
            if not resolved_incidents: return f"No resolved incidents found for group '{group_name}' to calculate metrics."
            total_duration = 0
            count = 0
            for item in resolved_incidents:
                created_at_str = item.get('sys_created_on')
                resolved_at_str = item.get('resolved_at')
                if created_at_str and resolved_at_str:
                    created_at = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
                    resolved_at = datetime.strptime(resolved_at_str, '%Y-%m-%d %H:%M:%S')
                    duration = resolved_at - created_at
                    total_duration += duration.total_seconds()
                    count += 1
            if count == 0: return f"Could not calculate metrics for group '{group_name}' due to missing data."
            avg_duration_seconds = total_duration / count
            avg_duration_minutes = avg_duration_seconds / 60
            avg_duration_hours = avg_duration_minutes / 60
            return f"Average time to resolve incidents for '{group_name}' is approximately {avg_duration_hours:.2f} hours."
        except Exception as e:
            return f"An error occurred while fetching metrics: {e}"
    def _arun(self, group_name: str): raise NotImplementedError()

# Insert this class definition into the "3. ServiceNow Custom Tool Definitions" section
class CountIncidentsForGroupInput(BaseModel):
    group_name: str = Field(description="The name of the assignment group, e.g., 'Hardware'.")

class CountIncidentsForGroupTool(BaseTool):
    name: str = "count_incidents_for_group"
    description: str = "Use this tool to get the total number of incidents for a specific assignment group."
    args_schema: Type[BaseModel] = CountIncidentsForGroupInput

    def _run(self, group_name: str):
        instance, user, pwd = get_servicenow_credentials()
        if not instance: return "ServiceNow credentials not configured."
        group_sys_id = get_sys_id(instance, user, pwd, "sys_user_group", "name", group_name)
        if not group_sys_id: return f"Could not find an assignment group named '{group_name}'."
        
        url = f"{instance}/api/now/stats/incident"
        params = {"sysparm_count": "true", "sysparm_query": f"assignment_group={group_sys_id}"}
        headers = {"Accept": "application/json"}
        
        try:
            response = requests.get(url, auth=(user, pwd), headers=headers, params=params)
            response.raise_for_status()
            count = response.json().get("result", {}).get("stats", {}).get("count", "0")
            return f"There are {count} incidents for the '{group_name}' assignment group."
        except Exception as e:
            return f"An error occurred while counting incidents: {e}"

    def _arun(self, group_name: str):
        raise NotImplementedError()

# Insert this class definition into the "3. ServiceNow Custom Tool Definitions" section
class ListIncidentsForGroupInput(BaseModel):
    group_name: str = Field(description="The name of the assignment group, e.g., 'Hardware'.")
    limit: int = Field(description="The maximum number of incidents to return, e.g., 5.")

class ListIncidentsForGroupTool(BaseTool):
    name: str = "list_incidents_for_group"
    description: str = "Use this tool to get a list of incidents assigned to a specific group."
    args_schema: Type[BaseModel] = ListIncidentsForGroupInput

    def _run(self, group_name: str, limit: int = 10):
        instance, user, pwd = get_servicenow_credentials()
        if not instance: return "ServiceNow credentials not configured."
        group_sys_id = get_sys_id(instance, user, pwd, "sys_user_group", "name", group_name)
        if not group_sys_id: return f"Could not find a group named '{group_name}'."
        
        url = f"{instance}/api/now/table/incident"
        params = {"sysparm_limit": str(limit), "sysparm_query": f"assignment_group={group_sys_id}", "sysparm_fields": "number,short_description,state"}
        headers = {"Accept": "application/json"}
        
        try:
            response = requests.get(url, auth=(user, pwd), headers=headers, params=params)
            response.raise_for_status()
            results = response.json().get("result", [])
            if not results: return f"No incidents found for '{group_name}'."
            
            formatted_results = [f"Found {len(results)} incidents for '{group_name}':"]
            for item in results:
                formatted_results.append(f"- {item.get('number')}: {item.get('short_description')} (State: {item.get('state')})")
            return "\n".join(formatted_results)
        except Exception as e:
            return f"An error occurred while listing incidents: {e}"
    
    def _arun(self, group_name: str, limit: int = 10):
        raise NotImplementedError()


# --- 4. LangChain Agent Setup ---
# --- MODIFIED: Swapped to a model that supports tool calling ---
llm = ChatNVIDIA(model="meta/llama-3.1-405b-instruct")

tools = [
    GetIncidentTool(), SearchIncidentsTool(), CreateIncidentTool(), UpdateIncidentTool(),
    ListOpenIncidentsForUserTool(), ListIncidentsAssignedToUserTool(),
    SearchKnowledgeBaseTool(), DeleteIncidentTool(), ResolveIncidentTool(), AssignIncidentTool(), GetIncidentMetricsTool(),
    CountIncidentsForGroupTool(), ListIncidentsForGroupTool(),
]
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful ServiceNow assistant. You have access to tools for incidents and the knowledge base. Always be friendly and conversational."),
    MessagesPlaceholder(variable_name="chat_history", optional=True),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])
agent = create_openai_tools_agent(llm, tools, prompt)

chat_histories = {}
agent_executor = AgentExecutor(
    agent=agent, 
    tools=tools, 
    verbose=True,
    handle_parsing_errors=True
)

# --- 5. FastAPI App and Endpoint ---
app = FastAPI(
    title="ServiceNow Chatbot API (NVIDIA Llama 3.1)",
    description="An API for interacting with a multi-tool ServiceNow agent with memory.",
    version="3.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def read_index():
    # This serves your index.html file at the root path
    return FileResponse('index.html')

app.mount("/static", StaticFiles(directory=".", html=True), name="static")

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default-session"

@app.post("/chat")
def handle_chat_request(request: ChatRequest):
    session_id = request.session_id
    if session_id not in chat_histories:
        chat_histories[session_id] = ConversationBufferWindowMemory(
            k=10, memory_key="chat_history", return_messages=True
        )
    memory = chat_histories[session_id]
    chat_history = memory.load_memory_variables({})['chat_history']
    print(f"Received message: '{request.message}' for session: {session_id}")

    # The key change is wrapping the logic in a try-except block
    try:
        response = agent_executor.invoke({
            "input": request.message,
            "chat_history": chat_history
        })
        
        # Save context to memory after successful invocation
        memory.save_context(
            {"input": request.message},
            {"output": response['output']}
        )
        print(f"Agent output: {response['output']}")
        
        # Return a JSONResponse with a 200 OK status
        return JSONResponse(content={"reply": response['output']})
    
    except Exception as e:
        print(f"An unexpected error occurred during agent execution: {e}")
        # Return a 500 Internal Server Error with the specific error message
        return JSONResponse(
            content={"reply": f"An unexpected error occurred: {str(e)}"},
            status_code=500
        )

@app.get("/")
def read_root():
    return {"status": "ServiceNow Chatbot API is running"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)