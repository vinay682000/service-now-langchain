
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
import json
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, validator, ValidationError
from sse_starlette.sse import EventSourceResponse
from typing import Type, List, Optional, Dict, Any, ClassVar

# --- LangChain Imports ---
#from langchain_nvidia_ai_endpoints import ChatNVIDIA # Using NVIDIA's library
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
class GetIncidentInput(BaseModel):
    incident_number: str = Field(description="The full incident number, e.g., 'INC0010001', 'INC0010025'.")
    include_fields: Optional[List[str]] = Field(
        default=None,
        description="List of fields to include. Available: number, short_description, description, state, priority, assignment_group, caller_id, sys_created_on, resolved_at, closed_at, category, subcategory, severity, impact, urgency, assigned_to, resolution_notes, close_notes, close_code, resolution_code, business_service, configuration_item, watch_list, active, reopened_count, reassignment_count, comments, work_notes"
    )
    verbose: Optional[bool] = Field(
        default=False,
        description="Whether to include additional metadata and raw field values. Default: False"
    )
    format: Optional[str] = Field(
        default="human",
        description="Output format. Options: 'human' (readable text), 'json' (raw data), 'minimal' (brief summary). Default: 'human'"
    )

    @validator('incident_number')
    def validate_incident_number(cls, v):
        if not v.startswith('INC'):
            raise ValueError("Incident number must start with 'INC' prefix")
        if not v[3:].isdigit():
            raise ValueError("Incident number must have digits after 'INC' prefix")
        return v

    @validator('format')
    def validate_format(cls, v):
        valid_formats = ['human', 'json', 'minimal']
        if v not in valid_formats:
            raise ValueError(f"Format must be one of: {', '.join(valid_formats)}")
        return v

class GetIncidentTool(BaseTool):
    name: str = "get_incident_details"
    description: str = "Use this tool to get comprehensive details for a specific incident ticket. Supports multiple output formats and field selection."
    args_schema: Type[BaseModel] = GetIncidentInput
    
    # Class variables (not model fields) - using ClassVar annotation
    FIELD_DISPLAY_NAMES: ClassVar[Dict[str, str]] = {
        'number': 'Incident Number',
        'short_description': 'Short Description',
        'description': 'Description',
        'state': 'State',
        'priority': 'Priority',
        'assignment_group': 'Assignment Group',
        'caller_id': 'Caller',
        'sys_created_on': 'Created On',
        'resolved_at': 'Resolved At',
        'closed_at': 'Closed At',
        'category': 'Category',
        'subcategory': 'Subcategory',
        'severity': 'Severity',
        'impact': 'Impact',
        'urgency': 'Urgency',
        'assigned_to': 'Assigned To',
        'resolution_notes': 'Resolution Notes',
        'close_notes': 'Close Notes',
        'close_code': 'Close Code',
        'resolution_code': 'Resolution Code',
        'business_service': 'Business Service',
        'configuration_item': 'Configuration Item',
        'watch_list': 'Watch List',
        'active': 'Active',
        'reopened_count': 'Reopened Count',
        'reassignment_count': 'Reassignment Count',
        'comments': 'Comments',
        'work_notes': 'Work Notes'
    }

    STATE_MAP: ClassVar[Dict[str, str]] = {
        '1': 'New 🆕',
        '2': 'In Progress 🚧',
        '3': 'On Hold ⏸️',
        '4': 'Awaiting User Info ℹ️',
        '5': 'Awaiting Problem ❓',
        '6': 'Resolved ✅',
        '7': 'Closed 🔒'
    }

    PRIORITY_MAP: ClassVar[Dict[str, str]] = {
        '1': 'Critical 🔴',
        '2': 'High 🟠',
        '3': 'Moderate 🟡',
        '4': 'Low 🟢',
        '5': 'Planning 🔵'
    }

    def _run(self, incident_number: str, include_fields: Optional[List[str]] = None,
             verbose: bool = False, format: str = "human"):
        
        tool_start_time = time.time()
        logger.info(f"🛠️  GetIncidentTool started for: {incident_number}")
        
        instance, user, pwd = get_servicenow_credentials()
        if not instance: 
            logger.error("❌ ServiceNow credentials not configured.")
            return "ServiceNow credentials not configured."
        
        # Default fields if none specified
        default_fields = ["number", "short_description", "description", "state", "priority", 
                         "assignment_group", "caller_id", "sys_created_on"]
        
        fields_to_include = include_fields if include_fields else default_fields
        fields_param = ",".join(fields_to_include)
        
        url = f"{instance}/api/now/table/incident"
        params = {
            "sysparm_query": f"number={incident_number}", 
            "sysparm_limit": "1", 
            "sysparm_fields": fields_param,
            "sysparm_display_value": "all"
        }
        headers = {"Accept": "application/json"}
        
        api_start_time = time.time()
        logger.info(f"🌐 API call for: {incident_number}")
        
        try:
            response = requests.get(url, auth=(user, pwd), headers=headers, params=params, timeout=30)
            api_time = time.time() - api_start_time
            logger.info(f"✅ API response in: {api_time:.2f}s")
            
            response.raise_for_status()
            data = response.json()
            
            results = data.get("result", [])
            if not results: 
                logger.warning(f"⚠️  No incident found: {incident_number}")
                return f"No incident found with number: {incident_number}"
            
            incident_data = results[0]
            
            # Format based on requested output
            if format == "json":
                result = json.dumps(incident_data, indent=2)
            elif format == "minimal":
                result = self._format_minimal(incident_data)
            else:
                result = self._format_human_readable(incident_data, fields_to_include, verbose)
            
            total_time = time.time() - tool_start_time
            logger.info(f"🏁 Tool completed in: {total_time:.2f}s")
            
            return result
            
        except requests.exceptions.Timeout:
            api_time = time.time() - api_start_time
            logger.error(f"⏰ Timeout after {api_time:.2f}s")
            return f"Error: Request timed out after {api_time:.2f} seconds."
            
        except requests.exceptions.HTTPError as err:
            api_time = time.time() - api_start_time
            logger.error(f"❌ HTTP error: {err}")
            if err.response.status_code == 404:
                return f"Incident {incident_number} not found."
            return f"HTTP error: {err}"
            
        except Exception as e:
            api_time = time.time() - api_start_time
            logger.error(f"🔥 Unexpected error: {e}")
            return f"Error: {str(e)}"

    def _format_human_readable(self, incident_data: Dict[str, Any], fields: List[str], verbose: bool) -> str:
        """Clean human-readable format"""
        lines = [f"📋 **Incident Details**", ""]
        
        for field in fields:
            if field in incident_data:
                display_name = self.FIELD_DISPLAY_NAMES.get(field, field.replace('_', ' ').title())
                value = self._get_display_value(incident_data[field], field)
                
                if value and value != 'N/A':
                    lines.append(f"• **{display_name}**: {value}")
        
        return "\n".join(lines)

    def _format_minimal(self, incident_data: Dict[str, Any]) -> str:
        """Minimal format for quick overview"""
        number = self._get_display_value(incident_data.get('number'), 'number')
        description = self._get_display_value(incident_data.get('short_description'), 'short_description')
        state = self._get_display_value(incident_data.get('state'), 'state')
        
        return f"{number}: {description} | {state}"

    def _get_display_value(self, field_data: Any, field_name: str) -> str:
        """Extract display value safely"""
        if field_data is None:
            return 'N/A'
        
        if isinstance(field_data, dict):
            return field_data.get('display_value', 'N/A')
        
        # Apply special formatting
        if field_name == 'state':
            return self.STATE_MAP.get(str(field_data), f"Unknown ({field_data})")
        
        if field_name == 'priority':
            return self.PRIORITY_MAP.get(str(field_data), f"Unknown ({field_data})")
        
        return str(field_data) if field_data else 'N/A'

    def _arun(self, incident_number: str, include_fields: Optional[List[str]] = None,
              verbose: bool = False, format: str = "human"):
        raise NotImplementedError()  


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
    close_code: str = Field(description="The close code. Valid values: Duplicate, Known error, No resolution provided, Resolved by caller, Resolved by change, Resolved by problem, Resolved by request, Solution provided, Workaround provided, User error")
class ResolveIncidentTool(BaseTool):
    name: str = "resolve_incident"
    description: str = "Use this tool to resolve and close an incident ticket. Requires a resolution note and close code."
    args_schema: Type[BaseModel] = ResolveIncidentInput

    def _run(self, incident_number: str, resolution_note: str, close_code: str = "Solution provided"):
        instance, user, pwd = get_servicenow_credentials()
        if not instance: 
            return "ServiceNow credentials not configured."
        incident_sys_id = get_sys_id(instance, user, pwd, "incident", "number", incident_number)
        if not incident_sys_id: 
            return f"Could not find incident {incident_number} to resolve."
        url = f"{instance}/api/now/table/incident/{incident_sys_id}"
        
        # CORRECT PAYLOAD - using close_code instead of resolution_code
        payload = {
            "state": "6",
            "resolution_notes": resolution_note,
            "close_notes": resolution_note,
            "close_code": close_code  # This is the mandatory field
        }
        
        headers = {"Content-Type": "application/json", "Accept": "application/json"}      
        try:
            response = requests.patch(url, auth=(user, pwd), headers=headers, json=payload)
            response.raise_for_status()
            return f"Successfully resolved incident {incident_number} with close code '{close_code}' and note: '{resolution_note}'."
        
        except requests.exceptions.HTTPError as err:
            if err.response.status_code == 400:
                error_detail = err.response.json().get('error', {}).get('detail', 'Unknown error')
                return f"Validation error: {error_detail}"
            elif err.response.status_code == 403:
                return f"Permission denied: {err}"
            else:
                return f"HTTP error occurred: {err}"
        
        except Exception as e:
            return f"An unexpected error occurred: {e}"
    
    def _arun(self, incident_number: str, resolution_note: str, close_code: str = "Solution provided"):
        raise NotImplementedError()
        
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
    group_name: str = Field(description="The name of the assignment group, e.g., 'Hardware', 'Software', 'Network'.")
    timeframe: Optional[str] = Field(
        default="last 30 days",
        description="Time period for metrics. Examples: 'last 7 days', 'this month', 'last quarter', 'last 90 days', '2024-01-01 to 2024-01-31'. Default: 'last 30 days'"
    )
    metric_type: Optional[str] = Field(
        default="average",
        description="Type of metric to calculate. Options: 'average', 'median', 'min', 'max', 'all'. Default: 'average'"
    )
    resolution_state: Optional[str] = Field(
        default="6",
        description="Which resolved state to consider. '6' (Resolved) or '7' (Closed). Default: '6'"
    )
    include_breakdown: Optional[bool] = Field(
        default=False,
        description="Whether to include breakdown by priority or category. Default: False"
    )

    @validator('timeframe')
    def validate_timeframe(cls, v):
        if v and not any(keyword in v.lower() for keyword in ['day', 'month', 'quarter', 'year', 'to', '-']):
            raise ValueError("Timeframe should contain time references like 'days', 'month', or date range")
        return v

    @validator('metric_type')
    def validate_metric_type(cls, v):
        valid_types = ['average', 'median', 'min', 'max', 'all']
        if v.lower() not in valid_types:
            raise ValueError(f"Metric type must be one of: {', '.join(valid_types)}")
        return v.lower()

    @validator('resolution_state')
    def validate_resolution_state(cls, v):
        if v not in ['6', '7']:
            raise ValueError("Resolution state must be '6' (Resolved) or '7' (Closed)")
        return v
class GetIncidentMetricsTool(BaseTool):
    name: str = "get_incident_metrics"
    description: str = "Use this tool to get resolution time metrics for incidents assigned to a specific group. Can calculate average, median, min, max resolution times with various filters and timeframes."
    args_schema: Type[BaseModel] = GetIncidentMetricsInput

    def _run(self, group_name: str, timeframe: str = "last 30 days", 
             metric_type: str = "average", resolution_state: str = "6",
             include_breakdown: bool = False):
        
        instance, user, pwd = get_servicenow_credentials()
        if not instance: 
            return "ServiceNow credentials not configured."
        
        # Get group SYS_ID
        group_sys_id = get_sys_id(instance, user, pwd, "sys_user_group", "name", group_name)
        if not group_sys_id: 
            return f"Could not find an assignment group named '{group_name}'."
        
        # Build the query
        base_query = f"assignment_group={group_sys_id}^state={resolution_state}"
        
        # Add timeframe filter
        timeframe_query = self._parse_timeframe(timeframe)
        if timeframe_query:
            base_query += f"^{timeframe_query}"
        
        # Get all resolved incidents with timing data
        url = f"{instance}/api/now/table/incident"
        params = {
            "sysparm_query": base_query,
            "sysparm_fields": "number,opened_at,resolved_at,closed_at,sys_created_on,priority,category,severity",
            "sysparm_limit": "1000"  # Increased limit for better metrics
        }
        headers = {"Accept": "application/json"}
        
        try:
            response = requests.get(url, auth=(user, pwd), headers=headers, params=params)
            response.raise_for_status()
            
            results = response.json().get("result", [])
            
            if not results:
                return self._build_no_results_message(group_name, timeframe, resolution_state)
            
            # Calculate resolution times
            resolution_times = self._calculate_resolution_times(results)
            
            if not resolution_times:
                return f"No incidents with complete timing data found for '{group_name}' group in {timeframe}."
            
            # Generate metrics based on requested type
            return self._generate_metrics_report(resolution_times, group_name, timeframe, 
                                               metric_type, resolution_state, include_breakdown, results)
            
        except requests.exceptions.HTTPError as err:
            if err.response.status_code == 403:
                return f"Permission denied while fetching metrics for group '{group_name}'. Please check user permissions."
            else:
                return f"HTTP error occurred while fetching metrics: {err}"
        except Exception as e:
            return f"An unexpected error occurred while fetching metrics: {e}"

    def _parse_timeframe(self, timeframe: str) -> str:
        """Convert natural language timeframe to ServiceNow query"""
        timeframe = timeframe.lower()
        
        time_mappings = {
            "last 7 days": "sys_created_on>=javascript:gs.daysAgoStart(7)^sys_created_on<=javascript:gs.daysAgoEnd(0)",
            "last 30 days": "sys_created_on>=javascript:gs.daysAgoStart(30)^sys_created_on<=javascript:gs.daysAgoEnd(0)",
            "last 90 days": "sys_created_on>=javascript:gs.daysAgoStart(90)^sys_created_on<=javascript:gs.daysAgoEnd(0)",
            "this month": "sys_created_on>=javascript:gs.beginningOfThisMonth()^sys_created_on<=javascript:gs.endOfThisMonth()",
            "last month": "sys_created_on>=javascript:gs.beginningOfLastMonth()^sys_created_on<=javascript:gs.endOfLastMonth()",
            "this quarter": "sys_created_on>=javascript:gs.beginningOfThisQuarter()^sys_created_on<=javascript:gs.endOfThisQuarter()",
            "last quarter": "sys_created_on>=javascript:gs.beginningOfLastQuarter()^sys_created_on<=javascript:gs.endOfLastQuarter()"
        }
        
        if timeframe in time_mappings:
            return time_mappings[timeframe]
        elif "to" in timeframe or "-" in timeframe:
            dates = timeframe.split(" to ") if " to " in timeframe else timeframe.split("-")
            if len(dates) == 2:
                start_date, end_date = dates[0].strip(), dates[1].strip()
                return f"sys_created_on>={start_date}^sys_created_on<={end_date}"
        
        return ""

    def _calculate_resolution_times(self, incidents: List[dict]) -> List[float]:
        """Calculate resolution times in hours for all incidents"""
        resolution_times = []
        
        for incident in incidents:
            # Try different timestamp field combinations
            start_time = incident.get('opened_at') or incident.get('sys_created_on')
            end_time = incident.get('resolved_at') or incident.get('closed_at')
            
            if start_time and end_time:
                try:
                    # Parse timestamps (adjust format based on your ServiceNow)
                    start_dt = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
                    end_dt = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
                    
                    # Calculate duration in hours
                    duration_hours = (end_dt - start_dt).total_seconds() / 3600
                    resolution_times.append(duration_hours)
                    
                except ValueError:
                    # Handle different date formats if needed
                    continue
        
        return resolution_times

    def _generate_metrics_report(self, resolution_times: List[float], group_name: str,
                                timeframe: str, metric_type: str, resolution_state: str,
                                include_breakdown: bool, all_incidents: List[dict]) -> str:
        """Generate comprehensive metrics report"""
        
        # Calculate all statistics
        stats = {
            'average': sum(resolution_times) / len(resolution_times),
            'median': sorted(resolution_times)[len(resolution_times) // 2],
            'min': min(resolution_times),
            'max': max(resolution_times),
            'count': len(resolution_times),
            'total_incidents': len(all_incidents)
        }
        
        # Build the report
        report = [
            f"📊 Resolution Metrics for '{group_name}' Group",
            f"• Timeframe: {timeframe}",
            f"• Resolution State: {'Resolved (6)' if resolution_state == '6' else 'Closed (7)'}",
            f"• Incidents Analyzed: {stats['count']} of {stats['total_incidents']} total",
            ""
        ]
        
        # Add requested metrics
        if metric_type == 'all':
            report.extend([
                f"⏱️  Average Resolution Time: {stats['average']:.1f} hours",
                f"📈 Median Resolution Time: {stats['median']:.1f} hours", 
                f"⚡ Fastest Resolution: {stats['min']:.1f} hours",
                f"🐢 Slowest Resolution: {stats['max']:.1f} hours"
            ])
        else:
            metric_titles = {
                'average': 'Average Resolution Time',
                'median': 'Median Resolution Time', 
                'min': 'Fastest Resolution Time',
                'max': 'Slowest Resolution Time'
            }
            report.append(f"⏱️  {metric_titles[metric_type]}: {stats[metric_type]:.1f} hours")
        
        # Add breakdown if requested
        if include_breakdown:
            breakdown = self._generate_breakdown(all_incidents, resolution_times)
            if breakdown:
                report.extend(["", "📋 Breakdown:", breakdown])
        
        return "\n".join(report)

    def _generate_breakdown(self, incidents: List[dict], resolution_times: List[float]) -> str:
        """Generate breakdown by priority or category"""
        # Implement breakdown logic based on available data
        return "Breakdown feature coming soon. Use include_breakdown=True to enable."

    def _build_no_results_message(self, group_name: str, timeframe: str, resolution_state: str) -> str:
        """Build message when no incidents found"""
        state_name = "Resolved" if resolution_state == "6" else "Closed"
        return f"No {state_name.lower()} incidents found for '{group_name}' group in {timeframe}."

    def _arun(self, group_name: str, timeframe: str = "last 30 days", 
              metric_type: str = "average", resolution_state: str = "6",
              include_breakdown: bool = False):
        raise NotImplementedError()

class CountIncidentsForGroupInput(BaseModel):
    group_name: str = Field(description="The name of the assignment group, e.g., 'Hardware', 'Software', 'Network'.")
    state: Optional[str] = Field(
        default=None, 
        description="Filter by incident state. Examples: '1' (New), '2' (In Progress), '6' (Resolved), '7' (Closed). Leave empty for all states."
    )
    timeframe: Optional[str] = Field(
        default=None,
        description="Time period filter. Examples: 'last 7 days', 'this month', 'last quarter', '2024-01-01 to 2024-01-31'"
    )
    priority: Optional[str] = Field(
        default=None,
        description="Filter by priority. Examples: '1' (Critical), '2' (High), '3' (Moderate), '4' (Low), '5' (Planning)"
    )

    @validator('timeframe')
    def validate_timeframe(cls, v):
        if v and not any(keyword in v.lower() for keyword in ['day', 'month', 'quarter', 'year', 'to', '-']):
            raise ValueError("Timeframe should contain time references like 'days', 'month', or date range 'yyyy-mm-dd to yyyy-mm-dd'")
        return v
class CountIncidentsForGroupTool(BaseTool):
    name: str = "count_incidents_for_group"
    description: str = "Use this tool to get the total number of incidents for a specific assignment group with optional filters for state, timeframe, and priority."
    args_schema: Type[BaseModel] = CountIncidentsForGroupInput

    def _run(self, group_name: str, state: Optional[str] = None, 
             timeframe: Optional[str] = None, priority: Optional[str] = None):
        instance, user, pwd = get_servicenow_credentials()
        if not instance: 
            return "ServiceNow credentials not configured."
        
        # Get group SYS_ID
        group_sys_id = get_sys_id(instance, user, pwd, "sys_user_group", "name", group_name)
        if not group_sys_id: 
            return f"Could not find an assignment group named '{group_name}'."
        
        # Build the query
        base_query = f"assignment_group={group_sys_id}"
        
        if state:
            base_query += f"^state={state}"
        
        if priority:
            base_query += f"^priority={priority}"
        
        # Handle timeframe
        if timeframe:
            timeframe_query = self._parse_timeframe(timeframe)
            if timeframe_query:
                base_query += f"^{timeframe_query}"
        
        url = f"{instance}/api/now/stats/incident"
        params = {
            "sysparm_count": "true", 
            "sysparm_query": base_query
        }
        headers = {"Accept": "application/json"}
        
        try:
            response = requests.get(url, auth=(user, pwd), headers=headers, params=params)
            response.raise_for_status()
            
            count = response.json().get("result", {}).get("stats", {}).get("count", "0")
            
            # Build informative response
            response_text = f"There are {count} incidents"
            if state:
                response_text += f" in state '{state}'"
            if timeframe:
                response_text += f" from {timeframe}"
            if priority:
                response_text += f" with priority '{priority}'"
            response_text += f" for the '{group_name}' assignment group."
            
            return response_text
            
        except requests.exceptions.HTTPError as err:
            if err.response.status_code == 403:
                return f"Permission denied while counting incidents for group '{group_name}'. Please check user permissions."
            else:
                return f"HTTP error occurred while counting incidents: {err}"
        except Exception as e:
            return f"An unexpected error occurred while counting incidents: {e}"

    def _parse_timeframe(self, timeframe: str) -> str:
        """Convert natural language timeframe to ServiceNow query"""
        timeframe = timeframe.lower()
        now = datetime.now()
        
        if "last 7 days" in timeframe:
            return f"sys_created_on>=javascript:gs.daysAgoStart(7)^sys_created_on<=javascript:gs.daysAgoEnd(0)"
        elif "last 30 days" in timeframe:
            return f"sys_created_on>=javascript:gs.daysAgoStart(30)^sys_created_on<=javascript:gs.daysAgoEnd(0)"
        elif "this month" in timeframe:
            return f"sys_created_on>=javascript:gs.beginningOfThisMonth()^sys_created_on<=javascript:gs.endOfThisMonth()"
        elif "last month" in timeframe:
            return f"sys_created_on>=javascript:gs.beginningOfLastMonth()^sys_created_on<=javascript:gs.endOfLastMonth()"
        elif "this quarter" in timeframe:
            return f"sys_created_on>=javascript:gs.beginningOfThisQuarter()^sys_created_on<=javascript:gs.endOfThisQuarter()"
        elif "to" in timeframe or "-" in timeframe:
            # Handle date ranges like "2024-01-01 to 2024-01-31"
            dates = timeframe.split(" to ") if " to " in timeframe else timeframe.split("-")
            if len(dates) == 2:
                start_date, end_date = dates[0].strip(), dates[1].strip()
                return f"sys_created_on>={start_date}^sys_created_on<={end_date}"
        
        return ""

    def _arun(self, group_name: str, state: Optional[str] = None, 
              timeframe: Optional[str] = None, priority: Optional[str] = None):
        raise NotImplementedError()

class ListIncidentsForGroupInput(BaseModel):
    group_name: str = Field(description="The name of the assignment group, e.g., 'Hardware', 'Software', 'Network'.")
    limit: int = Field(default=5, description="The maximum number of incidents to return. Default is 5, maximum is 50.")
    state: Optional[str] = Field(
        default=None, 
        description="Filter by incident state. Examples: '1' (New), '2' (In Progress), '6' (Resolved), '7' (Closed). Leave empty for all states."
    )
    timeframe: Optional[str] = Field(
        default=None,
        description="Time period filter. Examples: 'last 7 days', 'this month', 'last 30 days', '2024-01-01 to 2024-01-31'"
    )
    priority: Optional[str] = Field(
        default=None,
        description="Filter by priority. Examples: '1' (Critical), '2' (High), '3' (Moderate), '4' (Low), '5' (Planning)"
    )
    sort_by: Optional[str] = Field(
        default="newest",
        description="Sort order. Options: 'newest', 'oldest', 'priority_high', 'priority_low'. Default is 'newest'."
    )
    show_fields: Optional[List[str]] = Field(
        default_factory=lambda: ["number", "short_description", "state", "priority", "opened_at"],
        description="List of fields to include. Available: number, short_description, state, priority, opened_at, resolved_at, assignment_group, assigned_to, category, severity"
    )

    @validator('limit')
    def validate_limit(cls, v):
        if v > 50:
            raise ValueError("Limit cannot exceed 50 incidents for performance reasons.")
        if v < 1:
            raise ValueError("Limit must be at least 1.")
        return v

    @validator('timeframe')
    def validate_timeframe(cls, v):
        if v and not any(keyword in v.lower() for keyword in ['day', 'month', 'quarter', 'year', 'to', '-']):
            raise ValueError("Timeframe should contain time references like 'days', 'month', or date range")
        return v
class ListIncidentsForGroupTool(BaseTool):
    name: str = "list_incidents_for_group"
    description: str = "Use this tool to get a list of incidents assigned to a specific group with various filtering, sorting, and field selection options."
    args_schema: Type[BaseModel] = ListIncidentsForGroupInput

    def _run(self, group_name: str, limit: int = 5, state: Optional[str] = None,
             timeframe: Optional[str] = None, priority: Optional[str] = None,
             sort_by: str = "newest", show_fields: Optional[List[str]] = None):
        
        instance, user, pwd = get_servicenow_credentials()
        if not instance: 
            return "ServiceNow credentials not configured."
        
        # Get group SYS_ID
        group_sys_id = get_sys_id(instance, user, pwd, "sys_user_group", "name", group_name)
        if not group_sys_id: 
            return f"Could not find an assignment group named '{group_name}'."
        
        # Build the query
        base_query = f"assignment_group={group_sys_id}"
        
        if state:
            base_query += f"^state={state}"
        
        if priority:
            base_query += f"^priority={priority}"
        
        # Handle timeframe
        if timeframe:
            timeframe_query = self._parse_timeframe(timeframe)
            if timeframe_query:
                base_query += f"^{timeframe_query}"
        
        # Build fields parameter
        default_fields = ["number", "short_description", "state", "priority", "opened_at"]
        fields_to_show = show_fields if show_fields else default_fields
        fields_param = ",".join(fields_to_show)
        
        # Build orderby parameter
        order_mapping = {
            "newest": "opened_at DESC",
            "oldest": "opened_at ASC", 
            "priority_high": "priority ASC,opened_at DESC",
            "priority_low": "priority DESC,opened_at DESC"
        }
        orderby_param = order_mapping.get(sort_by, "opened_at DESC")
        
        url = f"{instance}/api/now/table/incident"
        params = {
            "sysparm_query": base_query,
            "sysparm_fields": fields_param,
            "sysparm_limit": str(limit),
            "sysparm_orderby": orderby_param
        }
        headers = {"Accept": "application/json"}
        
        try:
            response = requests.get(url, auth=(user, pwd), headers=headers, params=params)
            response.raise_for_status()
            
            results = response.json().get("result", [])
            
            if not results:
                return self._build_no_results_message(group_name, state, timeframe, priority)
            
            return self._format_results(results, group_name, len(results), state, timeframe, priority, fields_to_show)
            
        except requests.exceptions.HTTPError as err:
            if err.response.status_code == 403:
                return f"Permission denied while listing incidents for group '{group_name}'. Please check user permissions."
            else:
                return f"HTTP error occurred while listing incidents: {err}"
        except Exception as e:
            return f"An unexpected error occurred while listing incidents: {e}"

    def _parse_timeframe(self, timeframe: str) -> str:
        """Convert natural language timeframe to ServiceNow query"""
        timeframe = timeframe.lower()
        
        if "last 7 days" in timeframe:
            return "sys_created_on>=javascript:gs.daysAgoStart(7)^sys_created_on<=javascript:gs.daysAgoEnd(0)"
        elif "last 30 days" in timeframe:
            return "sys_created_on>=javascript:gs.daysAgoStart(30)^sys_created_on<=javascript:gs.daysAgoEnd(0)"
        elif "this month" in timeframe:
            return "sys_created_on>=javascript:gs.beginningOfThisMonth()^sys_created_on<=javascript:gs.endOfThisMonth()"
        elif "last month" in timeframe:
            return "sys_created_on>=javascript:gs.beginningOfLastMonth()^sys_created_on<=javascript:gs.endOfLastMonth()"
        elif "to" in timeframe or "-" in timeframe:
            dates = timeframe.split(" to ") if " to " in timeframe else timeframe.split("-")
            if len(dates) == 2:
                start_date, end_date = dates[0].strip(), dates[1].strip()
                return f"sys_created_on>={start_date}^sys_created_on<={end_date}"
        
        return ""

    def _build_no_results_message(self, group_name: str, state: Optional[str], 
                                 timeframe: Optional[str], priority: Optional[str]) -> str:
        """Build informative message when no incidents found"""
        message = f"No incidents found for '{group_name}' group"
        
        filters = []
        if state:
            filters.append(f"state '{state}'")
        if timeframe:
            filters.append(f"timeframe '{timeframe}'")
        if priority:
            filters.append(f"priority '{priority}'")
        
        if filters:
            message += f" with filters: {', '.join(filters)}"
        
        return message + "."

    def _format_results(self, results: List[dict], group_name: str, count: int,
                       state: Optional[str], timeframe: Optional[str], 
                       priority: Optional[str], fields: List[str]) -> str:
        """Format the results in a readable way"""
        
        # Build header
        header = f"Found {count} incidents for '{group_name}' group"
        filters = []
        if state:
            filters.append(f"state '{state}'")
        if timeframe:
            filters.append(f"timeframe '{timeframe}'")
        if priority:
            filters.append(f"priority '{priority}'")
        
        if filters:
            header += f" (filters: {', '.join(filters)})"
        
        formatted_results = [header + ":"]
        
        # Format each incident
        for i, incident in enumerate(results, 1):
            incident_lines = [f"{i}. {incident.get('number', 'N/A')}:"]
            
            for field in fields:
                if field != 'number' and field in incident:
                    value = incident[field]
                    if value:  # Only show non-empty fields
                        field_display = field.replace('_', ' ').title()
                        incident_lines.append(f"   • {field_display}: {value}")
            
            formatted_results.append("\n".join(incident_lines))
        
        return "\n\n".join(formatted_results)

    def _arun(self, group_name: str, limit: int = 5, state: Optional[str] = None,
              timeframe: Optional[str] = None, priority: Optional[str] = None,
              sort_by: str = "newest", show_fields: Optional[List[str]] = None):
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
8. Use markdown formatting (headings, bullet points, code blocks, bold/italics) where appropriate for readability

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
        "http://studious-bassoon-xx7vwvqxq7jcvv4g-5173.app.github.dev",
        "https://studious-bassoon-xx7vwvqxq7jcvv4g-5174.app.github.dev",
        "http://studious-bassoon-xx7vwvqxq7jcvv4g-5174.app.github.dev",
        "https://studious-bassoon-xx7vwvqxq7jcvv4g-8000.app.github.dev",
        "http://studious-bassoon-xx7vwvqxq7jcvv4g-8000.app.github.dev",
        "https://studious-bassoon-xx7vwvqxq7jcvv4g-3000.app.github.dev",
        "http://studious-bassoon-xx7vwvqxq7jcvv4g-3000.app.github.dev",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://localhost:3000",
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
@app.post("/api/chat-stream")
async def handle_chat_request(chat_request: ChatRequest, request: Request = None):
    total_start_time = time.time()
    logger.info(f"📨 Received request - Session: {chat_request.session_id}, Message: '{chat_request.message}'")
    
    # Check if client wants streaming (via header)
    if request:
        accept_header = request.headers.get("accept", "")
        is_streaming = "text/event-stream" in accept_header
    else:
        is_streaming = False
    
    if not is_streaming:
        # Original non-streaming logic
        try:
            if chat_request.session_id not in chat_histories:
                chat_histories[chat_request.session_id] = {"messages": []}
                logger.info(f"🆕 New session created: {chat_request.session_id}")
            
            agent_start_time = time.time()
            try:
                response = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, 
                        lambda: agent_executor.invoke({
                            "input": chat_request.message,
                            "chat_history": chat_histories[chat_request.session_id]["messages"]
                        })
                    ),
                    timeout=80.0
                )
                agent_time = time.time() - agent_start_time
                logger.info(f"⏱️ Agent execution took: {agent_time:.2f}s")
                
            except asyncio.TimeoutError:
                logger.warning(f"⏰ Timeout after 80s - Message: '{chat_request.message}'")
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
            chat_histories[chat_request.session_id]["messages"].extend([
                HumanMessage(content=chat_request.message),
                AIMessage(content=response['output'])
            ])
            
            # Prevent history from growing too large
            if len(chat_histories[chat_request.session_id]["messages"]) > 20:
                chat_histories[chat_request.session_id]["messages"] = chat_histories[chat_request.session_id]["messages"][-10:]
            
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
    else:
        # Streaming response
        async def event_generator():
            try:
                if chat_request.session_id not in chat_histories:
                    chat_histories[chat_request.session_id] = {"messages": []}
                    logger.info(f"🆕 New session created: {chat_request.session_id}")
                
                # Get the full response first
                response = await asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: agent_executor.invoke({
                        "input": chat_request.message,
                        "chat_history": chat_histories[chat_request.session_id]["messages"]
                    })
                )
                
                # Stream the response token by token
                output_text = response['output']
                words = output_text.split()
                
                for i, word in enumerate(words):
                    # Send each word with a delay for smooth streaming
                    yield {
                        "event": "message",
                        "data": json.dumps({
                            "token": word + (" " if i < len(words) - 1 else ""),
                            "complete": False
                        })
                    }
                    await asyncio.sleep(0.05)
                
                # Send completion event
                yield {
                    "event": "complete",
                    "data": json.dumps({
                        "complete": True,
                        "full_message": output_text
                    })
                }
                
                # Update history after successful streaming
                chat_histories[chat_request.session_id]["messages"].extend([
                    HumanMessage(content=chat_request.message),
                    AIMessage(content=output_text)
                ])
                
            except asyncio.TimeoutError:
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "error": "Request timeout. Please try a simpler query."
                    })
                }
            except Exception as e:
                yield {
                    "event": "error", 
                    "data": json.dumps({
                        "error": f"Processing error: {str(e)}"
                    })
                }
        
        return EventSourceResponse(event_generator())

app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)