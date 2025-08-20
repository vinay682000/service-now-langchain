// frontend/src/api.js
const BACKEND_URL = "https://studious-bassoon-xx7vwvqxq7jcvv4g-8000.app.github.dev/api";

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
            const response = await fetch(`${BACKEND_URL}/chat`, {
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
                    try { errorData = await response.json(); } catch {}
                    throw new Error(errorData.reply || errorData.error || `Error: ${response.status}`);
                }
                
                let errorData = {};
                try { errorData = await response.json(); } catch {}
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