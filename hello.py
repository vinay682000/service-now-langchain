from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_core.messages import SystemMessage, HumanMessage

# Load environment variables
load_dotenv()

def test_chat_nvidia():
    try:
        # Initialize the ChatNVIDIA model with the same configuration as main.py
        llm = ChatNVIDIA(model="meta/llama-3.1-405b-instruct")
        
        # Create a simple prompt to test the model
        messages = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content="hi")
        ]
        
        # Invoke the model directly
        response = llm.invoke(messages)
        print(f"ChatNVIDIA direct response: {response}")
        print(f"Response type: {type(response)}")
        print(f"Response content type: {type(response.content) if hasattr(response, 'content') else 'No content attribute'}")
        return {"status": "success", "response": str(response), "response_type": str(type(response))}
    except Exception as e:
        print(f"Error in ChatNVIDIA direct test: {e}")
        return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    print("Testing ChatNVIDIA directly...")
    test_result = test_chat_nvidia()
    print(f"Test result: {test_result}")