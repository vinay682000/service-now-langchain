// frontend/src/api.js

// Use current window origin (protocol + host + port)
const BACKEND_URL = window.location.origin;

// Function to get bot response
export const getBotResponse = async (userMessage, sessionId) => {
  const payload = {
    message: userMessage,
    session_id: sessionId,
  };

  try {
    const response = await fetch(`${BACKEND_URL}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      credentials: 'include',  // include cookies if backend requires auth
    });

    if (!response.ok) {
      // Try to parse backend error message
      let errorData = {};
      try { errorData = await response.json(); } catch {}
      throw new Error(errorData.detail || `Backend error: ${response.status}`);
    }

    const data = await response.json();
    return data.reply;
  } catch (error) {
    console.error("Error fetching bot response:", error);
    throw error;
  }
};
