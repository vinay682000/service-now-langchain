
# File: main.py
# Description: An advanced multi-tool agent for ServiceNow.
# (MODIFIED: Swapped to a Llama 3.1 model that supports tool calling)

import uvicorn
import os
import requests
import asyncio
import concurrent.futures
import logging
import time
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator, ValidationError
from typing import Type, List, Optional

# --- LangChain Imports ---
from langchain_nvidia_ai_endpoints import ChatNVIDIA # Using NVIDIA's library
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import BaseTool
from langchain_openai import AzureChatOpenAI

# --- 1. Load Environment Variables ---
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Console output
        # logging.FileHandler('app.log')  # Uncomment for file logging
    ]
)
logger = logging.getLogger(__name__)

# --- 2. Helper Functions ---
def get_servicenow_credentials():
    instance = os.getenv("SERVICENOW_INSTANCE")
    user = os.getenv("SERVICENOW_USERNAME")
    pwd = os.getenv("SERVICENOW_PASSWORD")
    if not all([instance, user, pwd]): 
        return None, None, None
    return instance, user, pwd

def get_sys_id(instance, user, pwd, table, query_field, query_value):
    url = f"{instance}/api/now/table/{table}"
    params = {"sysparm_query": f"{query_field}={query_value}", "sysparm_limit": "1", "sysparm_fields": "sys_id"}
    headers = {"Accept": "application/json"}
    try:
        response = requests.get(url, auth=(user, pwd), headers=headers, params=params)
        response.raise_for_status()
        results = response.json().get("result", [])
        if results: 
            return results[0]['sys_id']
    except Exception as e: 
        print(f"Error getting sys_id: {e}")
    return None

# --- 3. ServiceNow Custom Tool Definitions ---
# Add this import at the top of your file if it's not already there

class GetIncidentInput(BaseModel):
    incident_number: str = Field(description="The full incident number, e.g., 'INC0010001'.")

class GetIncidentTool(BaseTool):
    name: str = "get_incident_details"
    description: str = "Use this tool to get details for a specific incident ticket. The incident number must be the full number, including the 'INC' prefix."
    args_schema: Type[BaseModel] = GetIncidentInput
    
    def _run(self, incident_number: str):
        # LOG 1: Tool started
        tool_start_time = time.time()
        logger.info(f"🛠️  Tool '{self.name}' started for incident: {incident_number}")
        
        instance, user, pwd = get_servicenow_credentials()
        if not instance: 
            logger.error("❌ ServiceNow credentials not configured.")
            return "ServiceNow credentials not configured."
        
        url = f"{instance}/api/now/table/incident"
        params = {
            "sysparm_query": f"number={incident_number}", 
            "sysparm_limit": "1", 
            "sysparm_fields": "number,short_description,description,state,assignment_group,caller_id,sys_created_on"
        }
        headers = {"Accept": "application/json"}
        
        # LOG 2: Before API call
        api_start_time = time.time()
        logger.info(f"🌐 Making ServiceNow API call to: {url}")
        
        try:
            # CRITICAL: Added timeout=30 seconds to prevent hanging forever
            response = requests.get(url, auth=(user, pwd), headers=headers, params=params, timeout=30)
            
            # LOG 3: API call finished, log the time
            api_time = time.time() - api_start_time
            logger.info(f"✅ ServiceNow API response received in: {api_time:.2f} seconds")
            
            response.raise_for_status()
            data = response.json()
            
            results = data.get("result", [])
            if not results: 
                logger.warning(f"⚠️  No incident found for: {incident_number}")
                return f"No incident found with the number {incident_number}."
            
            incident_data = results[0]
            
            # Simplified helper function for safe data access
            def get_value(field_name, default='N/A'):
                field_data = incident_data.get(field_name, {})
                if isinstance(field_data, dict):
                    return field_data.get('display_value', default)
                return field_data or default
            
            # Map state numbers to human-readable text
            state_map = {
                '1': 'New',
                '2': 'In Progress',
                '3': 'On Hold',
                '4': 'Awaiting User Info',
                '5': 'Awaiting Problem',
                '6': 'Resolved',
                '7': 'Closed'
            }
            
            state_display = state_map.get(str(get_value('state')), 'Unknown')
            
            formatted_result = (
                f"Incident Details for {get_value('number')}:\n"
                f"- Short Description: {get_value('short_description')}\n"
                f"- Description: {get_value('description', 'No description provided')}\n"
                f"- State: {state_display}\n"
                f"- Assignment Group: {get_value('assignment_group', 'Not assigned')}\n"
                f"- Caller: {get_value('caller_id')}\n"
                f"- Created On: {get_value('sys_created_on')}"
            )
            
            # LOG 4: Entire tool finished
            total_tool_time = time.time() - tool_start_time
            logger.info(f"🏁 Tool '{self.name}' completed in: {total_tool_time:.2f} seconds")
            
            return formatted_result
            
        except requests.exceptions.Timeout:
            # LOG 5: Timeout occurred
            api_time = time.time() - api_start_time
            logger.error(f"⏰ SERVICE NOW API TIMEOUT after {api_time:.2f}s for {incident_number}")
            return f"Error: The request to ServiceNow timed out after {api_time:.2f}s while fetching {incident_number}."
            
        except requests.exceptions.HTTPError as err:
            api_time = time.time() - api_start_time
            logger.error(f"❌ HTTP error after {api_time:.2f}s: {err}")
            return f"An HTTP error occurred: {err}"
        except Exception as e:
            api_time = time.time() - api_start_time
            logger.error(f"🔥 Unexpected error after {api_time:.2f}s: {e}")
            return f"An unexpected error occurred: {e}"
class SearchIncidentsInput(BaseModel):
    search_term: str = Field(description="Keyword or phrase to search for in incident short descriptions.")

class SearchIncidentsTool(BaseTool):
    name: str = "search_incidents"
    description: str = "Use this tool to search for incidents by a keyword. Returns a list of matching incidents."
    args_schema: Type[BaseModel] = SearchIncidentsInput

    def _run(self, search_term: str):
        instance, user, pwd = get_servicenow_credentials()
        if not instance: 
            return "ServiceNow credentials not configured."
        
        url = f"{instance}/api/now/table/incident"
        params = {"sysparm_query": f"short_descriptionLIKE{search_term}", "sysparm_limit": "5", "sysparm_fields": "number,short_description"}
        headers = {"Accept": "application/json"}
        
        try:
            response = requests.get(url, auth=(user, pwd), headers=headers, params=params)
            response.raise_for_status()
            results = response.json().get("result", [])
            
            if not results: 
                return f"No incidents found matching '{search_term}'."
            
            formatted_results = ["Found incidents:"]
            for item in results: 
                formatted_results.append(f"- {item.get('number')}: {item.get('short_description')}")
            return "\n".join(formatted_results)
            
        except Exception as e: 
            return f"An error occurred during search: {e}"

    def _arun(self, search_term: str): 
        raise NotImplementedError()



class CreateIncidentInput(BaseModel):
    short_description: str = Field(description="A brief summary of the issue for the new incident.")
class CreateIncidentTool(BaseTool):
    name: str = "create_incident"
    description: str = "Use this tool to create a new incident ticket. Provide a short description of the problem."
    args_schema: Type[BaseModel] = CreateIncidentInput
    def _run(self, short_description: str):
        instance, user, pwd = get_servicenow_credentials()
        if not instance: 
            return "ServiceNow credentials not configured."
        caller_sys_id = get_sys_id(instance, user, pwd, "sys_user", "name", "Abel Tuter")
        if not caller_sys_id: 
            return "Could not find the default caller 'Abel Tuter' to create the incident."
        url = f"{instance}/api/now/table/incident"
        payload = {"short_description": short_description, "caller_id": caller_sys_id, "urgency": "3", "impact": "3"}
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        try:
            response = requests.post(url, auth=(user, pwd), headers=headers, json=payload)
            response.raise_for_status()
            new_incident_number = response.json().get("result", {}).get("number", "UNKNOWN")
            return f"Successfully created new incident: {new_incident_number}."
        except Exception as e: 
            return f"An error occurred while creating the incident: {e}"
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
        if not instance: 
            return "ServiceNow credentials not configured."
        incident_sys_id = get_sys_id(instance, user, pwd, "incident", "number", incident_number)
        if not incident_sys_id: 
            return f"Could not find incident {incident_number} to update."
        url = f"{instance}/api/now/table/incident/{incident_sys_id}"
        payload = {"work_notes": work_note}
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        try:
            response = requests.patch(url, auth=(user, pwd), headers=headers, json=payload)
            response.raise_for_status()
            return f"Successfully added note to incident {incident_number}."
        except Exception as e: 
            return f"An error occurred while updating the incident: {e}"
    def _arun(self, incident_number: str, work_note: str): raise NotImplementedError()

class ListOpenIncidentsForUserInput(BaseModel):
    user_name: str = Field(description="The full name of the user, e.g., 'Beth Anglin'.")
class ListOpenIncidentsForUserTool(BaseTool):
    name: str = "list_open_incidents_for_caller"
    description: str = "Use this tool to list all OPEN incidents reported by a specific user (caller)."
    args_schema: Type[BaseModel] = ListOpenIncidentsForUserInput
    def _run(self, user_name: str):
        instance, user, pwd = get_servicenow_credentials()
        if not instance: 
            return "ServiceNow credentials not configured."
        caller_sys_id = get_sys_id(instance, user, pwd, "sys_user", "name", user_name)
        if not caller_sys_id: 
            return f"Could not find a user named '{user_name}'."
        url = f"{instance}/api/now/table/incident"
        params = {"sysparm_query": f"caller_id={caller_sys_id}^active=true", "sysparm_limit": "10", "sysparm_fields": "number,short_description,state"}
        headers = {"Accept": "application/json"}
        try:
            response = requests.get(url, auth=(user, pwd), headers=headers, params=params)
            response.raise_for_status()
            results = response.json().get("result", [])
            if not results: 
                return f"No open incidents found for {user_name}."
            formatted_results = [f"Open incidents for {user_name}:"]
            for item in results: 
                formatted_results.append(f"- {item.get('number')}: {item.get('short_description')} (State: {item.get('state')})")
            return "\n".join(formatted_results)
        except Exception as e: 
            return f"An error occurred: {e}"
    def _arun(self, user_name: str): raise NotImplementedError()

class ListIncidentsAssignedToUserInput(BaseModel):
    user_name: str = Field(description="The full name of the user, e.g., 'David Loo'.")
class ListIncidentsAssignedToUserTool(BaseTool):
    name: str = "list_incidents_assigned_to_user"
    description: str = "Use this tool to find all incidents (open or closed) assigned to a specific user."
    args_schema: Type[BaseModel] = ListIncidentsAssignedToUserInput
    def _run(self, user_name: str):
        instance, user, pwd = get_servicenow_credentials()
        if not instance: 
            return "ServiceNow credentials not configured."
        assignee_sys_id = get_sys_id(instance, user, pwd, "sys_user", "name", user_name)
        if not assignee_sys_id: 
            return f"Could not find a user named '{user_name}' to check assignments."
        url = f"{instance}/api/now/table/incident"
        params = {"sysparm_query": f"assigned_to={assignee_sys_id}", "sysparm_limit": "10", "sysparm_fields": "number,short_description,state"}
        headers = {"Accept": "application/json"}
        try:
            response = requests.get(url, auth=(user, pwd), headers=headers, params=params)
            response.raise_for_status()
            results = response.json().get("result", [])
            if not results: 
                return f"No incidents are currently assigned to {user_name}."
            formatted_results = [f"Incidents assigned to {user_name}:"]
            for item in results: 
                formatted_results.append(f"- {item.get('number')}: {item.get('short_description')} (State: {item.get('state')})")
            return "\n".join(formatted_results)
        except Exception as e: 
            return f"An error occurred: {e}"
    def _arun(self, user_name: str): raise NotImplementedError()

class SearchKnowledgeBaseInput(BaseModel):
    search_term: str = Field(
        description="The keyword or phrase to search for in the knowledge base."
    )
    search_field: Optional[str] = Field(
        default="short_description",
        description="The specific field to search within. Can be 'short_description', 'article_body', or another valid field name. Defaults to 'short_description'."
    )
    search_limit: Optional[int] = Field(
        default=3,
        description="The maximum number of articles to return. Defaults to 3."
    )
    category: Optional[str] = Field(
        default=None,
        description="An optional category name to filter the search results. Use this for more precise searches, e.g., 'IT', 'HR', etc."
    )

class SearchKnowledgeBaseTool(BaseTool):
    name: str = "search_knowledge_base"
    description: str = "Searches the ServiceNow knowledge base for articles. Use this tool for technical questions, how-tos, or any information about internal processes. " \
                        "The search is flexible and can be refined by a specific field or category. " \
                        "Example: search_knowledge_base(search_term='troubleshoot printer', search_field='article_body') " \
                        "or search_knowledge_base(search_term='onboarding guide', category='HR')"
    args_schema: Type[BaseModel] = SearchKnowledgeBaseInput

    def _run(self, 
             search_term: str, 
             search_field: str = "short_description", 
             search_limit: int = 3, 
             category: Optional[str] = None):
        
        instance, user, pwd = get_servicenow_credentials()
        if not all([instance, user, pwd]):
            return "ServiceNow credentials not configured. Please check the 'get_servicenow_credentials' function."
        
        # This is where the correction is made.
        # Ensure search_field is set to a default if the agent sends None
        if not search_field:
            search_field = "short_description"
        
        # Build the sysparm_query parameter.
        query_parts = [f"{search_field}LIKE{search_term}"]
        if category:
            query_parts.append(f"^categoryLIKE{category}")
            
        # Construct the params dictionary *before* printing or using it.
        params = {
            "sysparm_query": "".join(query_parts),
            "sysparm_limit": str(search_limit),
            "sysparm_fields": "number,short_description,article_body,sys_id,sys_view_count"
        }

        # Now you can safely use the url and params variables.
        # Note: the URL construction is now correctly handled without a double slash
        # by using .rstrip('/') on the instance variable, just to be safe.
        url = f"{instance.rstrip('/')}/api/now/table/kb_knowledge"
        
        print(f"Constructed URL: {url}")
        print(f"Constructed Params: {params}")

        headers = {"Accept": "application/json"}
        
        try:
            response = requests.get(url, auth=(user, pwd), headers=headers, params=params)
            response.raise_for_status()
            results = response.json().get("result", [])
            
            if not results:
                return f"No knowledge base articles found matching '{search_term}'."
            
            formatted_results = ["Found knowledge base articles:"]
            for item in results:
                title = item.get('short_description', 'No Title')
                body_html = item.get('article_body', '')
                
                clean_body = body_html.replace('</p>', ' ').replace('<p>', ' ').replace('<strong>', '').replace('</strong>', '').strip()
                
                if not clean_body or len(clean_body) < 10:
                    summary = "No detailed content available."
                else:
                    summary = clean_body[:250].strip() + ("..." if len(clean_body) > 250 else "")
                    
                formatted_results.append(
                    f"- {item.get('number')}: {title}\n"
                    f"  Link: {instance}/kb_view.do?sys_kb_id={item.get('sys_id')}\n"
                    f"  Summary: {summary}"
                )
            
            return "\n\n".join(formatted_results)
            
        except requests.exceptions.RequestException as e:
            return f"An HTTP error occurred: {e}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def _arun(self, **kwargs):
        """Asynchronous run is not implemented for this tool."""
        raise NotImplementedError()


class DeleteIncidentInput(BaseModel):
    incident_number: str = Field(description="The incident number to delete, e.g., 'INC0010001'.")
class DeleteIncidentTool(BaseTool):
    name: str = "delete_incident"
    description: str = "Use this tool to permanently delete an incident record. WARNING: This action cannot be undone."
    args_schema: Type[BaseModel] = DeleteIncidentInput
    def _run(self, incident_number: str):
        instance, user, pwd = get_servicenow_credentials()
        if not instance: 
            return "ServiceNow credentials not configured."
        incident_sys_id = get_sys_id(instance, user, pwd, "incident", "number", incident_number)
        if not incident_sys_id: 
            return f"Could not find incident {incident_number} to delete."
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
        if not instance: 
            return "ServiceNow credentials not configured."
        incident_sys_id = get_sys_id(instance, user, pwd, "incident", "number", incident_number)
        if not incident_sys_id: 
            return f"Could not find incident {incident_number} to resolve."
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
        if not instance: 
            return "ServiceNow credentials not configured."
         # Handle null values from LLM
        if assign_to_user == "null":
            assign_to_user = None
        if assign_to_group == "null": 
            assign_to_group = None
         # Validation
        if not assign_to_user and not assign_to_group:
            return "Please specify either a user or a group to assign the incident to."
        if assign_to_user and assign_to_group:
            return "Please provide either a user or a group, not both."

        incident_sys_id = get_sys_id(instance, user, pwd, "incident", "number", incident_number)
        if not incident_sys_id: 
            return f"Could not find incident {incident_number} to assign."
        url = f"{instance}/api/now/table/incident/{incident_sys_id}"
        payload = {}
        if assign_to_user and assign_to_group: 
            return "Please provide either a user or a group to assign the incident, not both."
        if assign_to_user:
            assignee_sys_id = get_sys_id(instance, user, pwd, "sys_user", "name", assign_to_user)
            if not assignee_sys_id: 
                return f"Could not find a user named '{assign_to_user}'."
            payload["assigned_to"] = assignee_sys_id
        elif assign_to_group:
            group_sys_id = get_sys_id(instance, user, pwd, "sys_user_group", "name", assign_to_group)
            if not group_sys_id: 
                return f"Could not find a group named '{assign_to_group}'."
            payload["assignment_group"] = group_sys_id
        else: 
            return "Please specify a user or a group to assign the incident to."
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
        if not instance: 
            return "ServiceNow credentials not configured."
        group_sys_id = get_sys_id(instance, user, pwd, "sys_user_group", "name", group_name)
        if not group_sys_id: 
            return f"Could not find an assignment group named '{group_name}'."
        url = f"{instance}/api/now/stats/incident"
        params = {"sysparm_query": f"assignment_group={group_sys_id}", "sysparm_count": "true", "sysparm_fields": "resolved_at", "sysparm_group_by": "assignment_group"}
        headers = {"Accept": "application/json"}
        try:
            response = requests.get(url, auth=(user, pwd), headers=headers, params=params)
            response.raise_for_status()
            results = response.json().get("result", [])
            if not results: 
                return f"No metrics found for group '{group_name}'."
            resolved_incidents = [item for item in results if item.get('resolved_at')]
            if not resolved_incidents: 
                return f"No resolved incidents found for group '{group_name}' to calculate metrics."
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
            if count == 0: 
                return f"Could not calculate metrics for group '{group_name}' due to missing data."
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
        if not instance: 
            return "ServiceNow credentials not configured."
        group_sys_id = get_sys_id(instance, user, pwd, "sys_user_group", "name", group_name)
        if not group_sys_id: 
            return f"Could not find an assignment group named '{group_name}'."
        
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
        if not instance: 
            return "ServiceNow credentials not configured."
        group_sys_id = get_sys_id(instance, user, pwd, "sys_user_group", "name", group_name)
        if not group_sys_id: 
            return f"Could not find a group named '{group_name}'."
        
        url = f"{instance}/api/now/table/incident"
        params = {"sysparm_limit": str(limit), "sysparm_query": f"assignment_group={group_sys_id}", "sysparm_fields": "number,short_description,state"}
        headers = {"Accept": "application/json"}
        
        try:
            response = requests.get(url, auth=(user, pwd), headers=headers, params=params)
            response.raise_for_status()
            results = response.json().get("result", [])
            if not results: 
                return f"No incidents found for '{group_name}'."
            
            formatted_results = [f"Found {len(results)} incidents for '{group_name}':"]
            for item in results:
                formatted_results.append(f"- {item.get('number')}: {item.get('short_description')} (State: {item.get('state')})")
            return "\n".join(formatted_results)
        except Exception as e:
            return f"An error occurred while listing incidents: {e}"
    
    def _arun(self, group_name: str, limit: int = 10):
        raise NotImplementedError()

class GetMultipleIncidentsInput(BaseModel):
    incident_numbers: List[str] = Field(description="List of incident numbers to fetch")
class GetMultipleIncidentsTool(BaseTool):
    name: str = "get_multiple_incidents"
    description: str = "Fetch details for multiple incidents concurrently. Input should be a list of incident numbers."
    args_schema: Type[BaseModel] = GetMultipleIncidentsInput

    def _run(self, incident_numbers: List[str]):
        instance, user, pwd = get_servicenow_credentials()
        if not instance:
            return "ServiceNow credentials not configured."

        def fetch_single_incident(inc_num):
            # Use the SAME API call as GetIncidentTool but with proper error handling
            url = f"{instance}/api/now/table/incident"
            params = {
                "sysparm_query": f"number={inc_num}",
                "sysparm_limit": "1",
                "sysparm_fields": "number,short_description,description,state,assignment_group,caller_id"
            }
            headers = {"Accept": "application/json"}
            
            try:
                response = requests.get(url, auth=(user, pwd), headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
                
                # Handle empty results
                if not data.get('result') or len(data['result']) == 0:
                    return f"Incident {inc_num} not found"
                
                incident = data['result'][0]
                
                # SAFE field access (same as GetIncidentTool)
                def get_display_value(field_data):
                    if isinstance(field_data, dict):
                        return field_data.get('display_value', 'N/A')
                    return 'N/A'
                
                assignment_group = incident.get('assignment_group')
                caller_id = incident.get('caller_id')
                
                # Handle empty assignment_group (string instead of dict)
                if assignment_group == "":  # This is the bug!
                    assignment_group_display = "Not assigned"
                else:
                    assignment_group_display = get_display_value(assignment_group)
                
                # Handle caller_id
                caller_display = get_display_value(caller_id) if caller_id else "Unknown"
                
                description = incident.get('description', '')
                if not description:
                    description = "No description provided"
                
                return (
                    f"Incident {inc_num}:\n"
                    f"- Short Description: {incident.get('short_description', 'Not provided')}\n"
                    f"- State: {incident.get('state', 'Unknown')}\n"
                    f"- Assignment Group: {assignment_group_display}\n"
                    f"- Caller: {caller_display}\n"
                    f"- Description: {description}"
                )
                
            except Exception as e:
                return f"Error fetching incident {inc_num}: {str(e)}"

        # Use ThreadPoolExecutor for concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(fetch_single_incident, incident_numbers))
            
        return "\n\n".join(results)


# --- 4. LangChain Agent Setup ---
# --- MODIFIED: Swapped to a model that supports tool calling ---
#llm = ChatNVIDIA(model="meta/llama-3.1-405b-instruct")
llm = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"), # e.g., "https://your-resource.openai.azure.com"
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version="2025-01-01-preview", # Use a recent version
    azure_deployment="gpt-4o-mini", # The name of your deployment in Azure portal
    temperature=0,
    max_tokens=500, # Enough for a response, but not too long
    timeout=10, # Fail fast if the model is slow
    request_timeout=10
)
    


tools = [
    GetIncidentTool(), SearchIncidentsTool(), CreateIncidentTool(), UpdateIncidentTool(),
    ListOpenIncidentsForUserTool(), ListIncidentsAssignedToUserTool(),
    SearchKnowledgeBaseTool(), DeleteIncidentTool(), ResolveIncidentTool(), AssignIncidentTool(), GetIncidentMetricsTool(),
    CountIncidentsForGroupTool(), ListIncidentsForGroupTool(), GetMultipleIncidentsTool(),
]
prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a helpful ServiceNow assistant. Follow these rules strictly:

1. When user asks for multiple incidents, use get_multiple_incidents tool ONCE
2. Present results in clean, natural language format - no JSON
3. If tool returns good data, present it directly without extra processing
4. Never ask follow-up questions unless user specifically asks for more
5. Keep responses concise but informative
6. For single incidents, use get_incident_details tool
7. Stop after presenting the requested information
8. NEVER use markdown formatting like **bold** or *italics* in your responses. Use plain text only.

Available capabilities: Get incident details, search knowledge base, create/update incidents, and more.

Always be professional and focused on providing the exact information requested."""),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])
agent = create_openai_tools_agent(llm, tools, prompt)

chat_histories = {}
agent_executor = AgentExecutor(
    agent=agent, 
    tools=tools, 
    verbose=True,
    handle_parsing_errors=True,
    max_iterations=4,
    early_stopping_method='force',
    return_intermediate_steps=False,
    max_execution_time=45
)

# --- 5. FastAPI App and Endpoint ---
app = FastAPI(
    title="ServiceNow Chatbot API (NVIDIA Llama 3.1)",
    description="An API for interacting with a multi-tool ServiceNow agent with memory.",
    version="3.1.0",
)

# Add GZip compression middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)  # Compress responses > 1KB

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://studious-bassoon-xx7vwvqxq7jcvv4g-5173.app.github.dev",
        "http://studious-bassoon-xx7vwvqxq7jcvv4g-5173.app.github.dev"
    ],
    allow_credentials=True,
    allow_methods=["POST", "OPTIONS", "GET"],  # Explicitly specify needed methods
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=600
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, description="User message to process")  # Required with length limits
    session_id: Optional[str] = Field(
        default="default-session",
        min_length=1,
        max_length=50,
        pattern=r'^[a-zA-Z0-9-_]+$',  # Only allow alphanumeric, dash, underscore
        description="Unique session identifier for conversation history"
    )

    @validator('message')
    def validate_message(cls, v):
        if not v or not v.strip():
            raise ValueError("Message cannot be empty or whitespace only")
        return v.strip()


@app.options("/api/chat")
async def options_handler():
    return JSONResponse(
        content={"status": "ok"},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS, GET",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "600"
        }
    )

@app.post("/api/chat")
async def handle_chat_request(request: ChatRequest):
    total_start_time = time.time()
    logger.info(f"📨 Received request - Session: {request.session_id}, Message: '{request.message}'")
    
    try:
        if request.session_id not in chat_histories:
            chat_histories[request.session_id] = {"messages": []}
            logger.info(f"🆕 New session created: {request.session_id}")
        
        # TIME THE AGENT EXECUTION
        agent_start_time = time.time()
        try:
            response = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: agent_executor.invoke({
                        "input": request.message,
                        "chat_history": chat_histories[request.session_id]["messages"]
                    })
                ),
                timeout=80.0
            )
            agent_time = time.time() - agent_start_time
            logger.info(f"⏱️ Agent execution took: {agent_time:.2f}s")
            
        except asyncio.TimeoutError:
            logger.warning(f"⏰ Timeout after 80s - Message: '{request.message}'")
            return JSONResponse(
                content={"reply": "This operation is taking longer than expected. Please try a simpler query or fewer incidents at once."},
                status_code=408
            )            
        except Exception as e:
            logger.error(f"❌ Agent execution failed: {str(e)}")
            return JSONResponse(
                content={"reply": "I encountered an error while processing your request. Please try again with a different query."},
                status_code=500
            )
        
        # Update chat history
        chat_histories[request.session_id]["messages"].extend([
            HumanMessage(content=request.message),
            AIMessage(content=response['output'])
        ])
        # Prevent history from growing too large
        if len(chat_histories[request.session_id]["messages"]) > 20:
            chat_histories[request.session_id]["messages"] = chat_histories[request.session_id]["messages"][-10:]
        
        total_time = time.time() - total_start_time
        logger.info(f"✅ Total request processed in {total_time:.2f}s")
        return {"reply": response['output']}
    
    except ValidationError as e:
        logger.warning(f"⚠️ Validation error: {str(e)}")
        return JSONResponse(
            content={"error": "Invalid request format. Please check your input."},
            status_code=400
        )
    except Exception as e:
        logger.error(f"🔥 Unexpected error: {str(e)}")
        return JSONResponse(
            content={"reply": "Our service is temporarily unavailable. Please try again in a moment."},
            status_code=500
        )
        
app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)