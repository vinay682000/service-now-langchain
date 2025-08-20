# frontend/src/tools.py
from langchain.tools import BaseTool

# Placeholder for your ServiceNow instance details
SN_INSTANCE_URL = "https://your_instance_name.service-now.com"
SN_USERNAME = "your_username"
SN_PASSWORD = "your_password"

class ServiceNowBaseTool(BaseTool):
    """Base class for all ServiceNow tools."""
    # This class can be extended with common authentication logic if needed.
    pass

class GetExcelReportTool(ServiceNowBaseTool):
    """
    Use this tool to generate a link to an Excel report of incidents based on various filters.
    The report can be filtered by the number of days to look back, incident status, and assignment group.
    """
    name = "get_excel_report_tool"
    description = (
        "Generates a download link for an Excel report of incidents. "
        "Parameters: days_ago (int), status (str), group (str). "
        "Example: `get_excel_report_tool(days_ago=30, status='Closed', group='Network Team')`"
    )

    def _run(self, days_ago: int = 30, status: str = None, group: str = None) -> str:
        # Build the URL with query parameters for the FastAPI endpoint
        base_url = "http://127.0.0.1:8000/report/incidents/excel"  # Use the local FastAPI URL
        params = {}
        if days_ago:
            params['days_ago'] = days_ago
        if status:
            params['status'] = status
        if group:
            params['group'] = group

        query_string = "&".join([f"{key}={value}" for key, value in params.items()])
        report_url = f"{base_url}?{query_string}"
        
        return (
            f"I have generated the Excel report link for you. "
            f"You can download it by clicking here: {report_url}"
        )

    def _arun(self, days_ago: int = 30, status: str = None, group: str = None):
        raise NotImplementedError("This tool does not support async.")

# Add your existing tools here, e.g.,
# class GetIncidentTool(ServiceNowBaseTool):
#    ...