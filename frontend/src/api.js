// frontend/src/api.js
const BACKEND_URL = "https://studious-bassoon-xx7vwvqxq7jcvv4g-8000.app.github.dev";

const getOrCreateSessionId = () => {
    let sessionId = localStorage.getItem('chatSessionId');
    if (!sessionId) {
        sessionId = `session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        localStorage.setItem('chatSessionId', sessionId);
    }
    return sessionId;
};

export const getBotResponse = async (userMessage) => {
    const requestId = `req_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`;
    const startTime = Date.now();
    
    console.time(`API_Call_${requestId}`);
    console.log(`🚀 Starting API call ${requestId}: "${userMessage.substring(0, 30)}${userMessage.length > 30 ? '...' : ''}"`);

    const sessionId = getOrCreateSessionId();
    const payload = {
        message: userMessage,
        session_id: sessionId,
    };

    const fetchWithRetry = async (attempt = 0) => {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 120000);

        try {
            const response = await fetch(`${BACKEND_URL}/api/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify(payload),
                mode: 'cors',
                credentials: 'omit',
                signal: controller.signal
            });

            const duration = Date.now() - startTime;
            console.timeEnd(`API_Call_${requestId}`);
            console.log(`✅ API call ${requestId} completed in ${duration}ms`);
            console.log('Memory usage:', Math.round(performance.memory.usedJSHeapSize / 1024 / 1024) + 'MB');

            clearTimeout(timeoutId);

            if (!response.ok) {
                if (response.status >= 400 && response.status < 500) {
                    let errorData = {};
                    try { errorData = await response.json(); } catch (e) {console.error("API request failed:", e);}
                    throw new Error(errorData.reply || errorData.error || `Error: ${response.status}`);
                }
                
                let errorData = {};
                try { errorData = await response.json(); } catch (e) {console.error("API request failed:", e);}
                throw new Error(errorData.detail || errorData.error || `Backend error: ${response.status}`);
            }

            const data = await response.json();
            return data;

        } catch (error) {
            clearTimeout(timeoutId);
            
            if (error.name === 'AbortError') {
                console.warn(`⏰ API call ${requestId} timed out after 120s`);
                throw new Error('This operation is taking longer than expected. Please try a simpler query.');
            }
            
            if (attempt < 1 && error.message.includes('Failed to fetch')) {
                console.log(`🔄 Retrying API call ${requestId}, attempt ${attempt + 1}`);
                await new Promise(resolve => setTimeout(resolve, 1000 * (attempt + 1)));
                return fetchWithRetry(attempt + 1);
            }
            
            console.error(`❌ API call ${requestId} failed:`, error);
            throw error;
        }
    };

    try {
        const response = await fetchWithRetry();
        return response.reply;
    } catch (error) {
        console.error("Chat API Error:", error);
        
        if (error.message.includes('timed out') || error.message.includes('longer than expected')) {
            throw new Error('The request is taking longer than expected. Complex queries may take up to 2 minutes.');
        } else if (error.message.includes('Failed to fetch')) {
            throw new Error('Network connection issue. Please check your connection and try again.');
        } else if (error.message.includes('Backend error')) {
            throw new Error('Service temporarily unavailable. Please try again shortly.');
        } else {
            throw new Error('Sorry, I encountered an issue processing your request. Please try again.');
        }
    }
};

// Streaming API call
export const getBotResponseStreaming = async (userMessage, callbacks) => {
    console.log("🔄 Starting streaming request...");
    const sessionId = getOrCreateSessionId();
    const payload = {
        message: userMessage,
        session_id: sessionId,
    };

    try {
        const url = `${BACKEND_URL}/api/chat-stream`;
        console.log("📡 Calling:", url);
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'text/event-stream',
            },
            body: JSON.stringify(payload),
        });

        console.log("✅ Response status:", response.status);
        console.log("✅ Content-Type:", response.headers.get('Content-Type'));
        console.log("✅ Response OK:", response.ok);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let fullMessage = '';
        let currentEvent = null;   // track current event type

        console.log("📥 Starting to read stream...");

        while (true) {
            const { value, done } = await reader.read();
            if (done) {
                console.log("🏁 Stream reading completed");
                break;
            }

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');

            for (let i = 0; i < lines.length; i++) {
                const line = lines[i].trim();
                if (!line) continue;

                console.log("🔍 Processing line:", line);

                if (line.startsWith('event: ')) {
                    currentEvent = line.slice(7).trim();
                    console.log("📌 Current event set to:", currentEvent);
                    continue;
                }

                if (line.startsWith('data: ')) {
                    try {
                        const data = line.slice(6);
                        const eventData = JSON.parse(data);
                        console.log("✅ Parsed event data:", eventData);

                        if (currentEvent === 'message') {
                            fullMessage += eventData.token;
                            callbacks.onToken?.(eventData.token, fullMessage);
                        } 
                        else if (currentEvent === 'complete') {
                            callbacks.onComplete?.(eventData.full_message || fullMessage);
                            return;
                        } 
                        else if (currentEvent === 'error') {
                            callbacks.onError?.(eventData.error || "Unknown streaming error");
                            return;
                        }
                    } catch (e) {
                        console.warn('❌ Failed to parse SSE data:', e, 'Line:', line);
                    }
                }
            }

            // keep last partial line in buffer
            buffer = lines[lines.length - 1];
        }
    } catch (error) {
        console.error('❌ Streaming error:', error);
        callbacks.onError?.(error.message);
    }
};


// Smart function that tries streaming first
export const getBotResponseSmart = async (userMessage, callbacks) => {
    console.log("🔍 getBotResponseSmart called");
    console.log("📋 Callbacks received:", Object.keys(callbacks));
    console.log("🎯 onToken callback exists:", typeof callbacks.onToken === 'function');
    console.log("🎯 onComplete callback exists:", typeof callbacks.onComplete === 'function');
    
    if (typeof callbacks.onToken === 'function') {
        console.log("🚀 Attempting streaming...");
        try {
            await getBotResponseStreaming(userMessage, callbacks);
            console.log("✅ Streaming completed successfully");
        } catch (error) {
            console.log("❌ Streaming failed:", error.message);
            console.log("🔄 Falling back to regular API...");
            // Fallback to regular API
            try {
                const response = await getBotResponse(userMessage);
                callbacks.onComplete?.(response);
                console.log("✅ Fallback API call succeeded");
            } catch (fallbackError) {
                console.log("❌ Fallback API also failed:", fallbackError.message);
                callbacks.onError?.(fallbackError.message);
            }
        }
    } else {
        console.log("📦 No onToken callback, using regular API directly");
        // Use regular API
        try {
            const response = await getBotResponse(userMessage);
            callbacks.onComplete?.(response);
            console.log("✅ Regular API call succeeded");
        } catch (error) {
            console.log("❌ Regular API failed:", error.message);
            callbacks.onError?.(error.message);
        }
    }
};