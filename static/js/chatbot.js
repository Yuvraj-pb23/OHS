const chatIcon = document.getElementById("chat-icon");
const chatBubble = document.getElementById("chat-bubble");
const chatbot = document.getElementById("chatbot");
const closeChat = document.getElementById("close-chat");
const sendBtn = document.getElementById("send-btn");
const userInput = document.getElementById("user-input");
const chatBody = document.getElementById("chat-body");
const chatHeader = document.querySelector(".chat-header");

let isChatOpen = false;
let isFirstTime = true;

// Pagination settings
const ITEMS_PER_PAGE = 5;

const botAvatarHTML = `
  <div class="message-avatar" style="width: 30px; height: 30px; border-radius: 50%; background: white; padding: 5px; display: flex; align-items: center; justify-content: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
    <img src="/static/images/RA-logo-1.png" alt="Bot Logo" style="width: 100%; height: 100%; object-fit: contain;">
  </div>
`;

function shrinkHeader() {
    chatHeader.classList.add('shrunk');
}

function expandHeader() {
    chatHeader.classList.remove('shrunk');
}

function createInitialMessage() {
    if (chatBody.children.length === 0) {
        const dateSeparator = document.createElement("div");
        dateSeparator.className = "date-separator";
        dateSeparator.textContent = "Today";
        chatBody.appendChild(dateSeparator);
    }
    const botMsgDiv = document.createElement("div");
    botMsgDiv.className = "bot-message";
    botMsgDiv.innerHTML = `${botAvatarHTML}<div class="message-bubble">Hi there! <br> How can I help you today?<br><br>You can type "ro" to see Regional Offices or "piu" to see Project Implementation Units.</div>`;
    chatBody.appendChild(botMsgDiv);
    chatBody.scrollTop = chatBody.scrollHeight;
}

function sendMessage() {
    const message = userInput.value.trim();
    if (message === "" || sendBtn.disabled) return;
    sendBtn.disabled = true;
    appendUserMessage(message);
    userInput.value = "";
    shrinkHeader();
    showTypingIndicator();
    fetchBotResponse(message);
}

function sendSelectionMessage(selectionText) {
    appendUserMessage(selectionText);
    shrinkHeader();
    showTypingIndicator();
    fetchBotResponse(selectionText);
}

function fetchBotResponse(message) {
    fetch("/chat/", {
        method: "POST",
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: message })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        hideTypingIndicator();
        console.log("Received response:", data); // Debug log
        handleBotResponse(data);
    })
    .catch((error) => {
        console.error("Fetch Error:", error);
        hideTypingIndicator();
        showErrorMessage();
    });
}

function appendUserMessage(message) {
    const userMsgDiv = document.createElement("div");
    userMsgDiv.className = "user-message";
    userMsgDiv.textContent = message;
    chatBody.appendChild(userMsgDiv);
    chatBody.scrollTop = chatBody.scrollHeight;
}

/**
 * ENHANCED: Better handling of all response types
 */
function handleBotResponse(data) {
    console.log("Processing response data:", data); // Debug log

    const response = data.response;
    const shouldReset = data.reset || false;

    if (shouldReset) {
        const botMsgDiv = document.createElement("div");
        botMsgDiv.className = "bot-message";
        botMsgDiv.innerHTML = `${botAvatarHTML}<div class="message-bubble">${response}</div>`;
        chatBody.appendChild(botMsgDiv);
        setTimeout(() => {
            chatBody.innerHTML = '';
            createInitialMessage();
            expandHeader();
        }, 2000);
        sendBtn.disabled = false;
        return;
    }

    const botMsgDiv = document.createElement("div");
    botMsgDiv.className = "bot-message";
    botMsgDiv.innerHTML = botAvatarHTML;
    chatBody.appendChild(botMsgDiv);

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    botMsgDiv.appendChild(bubble);

    if (typeof response === 'object' && response !== null) {
        if (response.display_type) {
            console.log("Processing structured response:", response.display_type); // Debug log
            switch (response.display_type) {
                case 'button_selection':
                    // Buttons should not be typed, so they are handled separately
                    createButtonSelectionMessage(bubble, response);
                    break;
                case 'text_block':
                    createTextBlockMessage(bubble, response);
                    break;
                case 'detailed_breakdown':
                    createDetailedBreakdownMessage(bubble, response);
                    break;
                default:
                    createFallbackMessage(bubble, response);
            }
        } else {
            createFallbackMessage(bubble, response);
        }
    } else {
        const responseText = String(response);
        if (!parseAndCreateSuggestions(bubble, responseText)) {
            // All text-based responses now use the universal typing function
            typeContent(bubble, responseText);
        }
    }

    chatBody.scrollTop = chatBody.scrollHeight;
    sendBtn.disabled = false;
}

/**
 * MODIFIED: Now generates an HTML string and passes it to the typeContent function.
 */
function createTextBlockMessage(bubble, responseData) {
    let htmlString = '';

    if (responseData.title) {
        htmlString += `<h3 style="margin: 0 0 10px 0; color: #2563eb; font-size: 16px;">${responseData.title}</h3>`;
    }

    if (responseData.lines && Array.isArray(responseData.lines)) {
        responseData.lines.forEach(line => {
            const content = line.trim() === '' ? '<br>' : line;
            htmlString += `<div style="margin-bottom: 4px; line-height: 1.4;">${content}</div>`;
        });
    }

    typeContent(bubble, htmlString);
}

/**
 * MODIFIED: Now generates an HTML string and passes it to the typeContent function.
 */
function createDetailedBreakdownMessage(bubble, responseData) {
    let htmlString = '';

    if (responseData.title) {
        htmlString += `<h3 style="margin: 0 0 15px 0; color: #2563eb; font-size: 16px;">${responseData.title}</h3>`;
    }

    if (responseData.total_count) {
        htmlString += `<div style="background: #f8fafc; padding: 10px; border-radius: 6px; margin-bottom: 15px; border-left: 3px solid #2563eb;">`;
        htmlString += `<div>Total Sections: ${responseData.total_count}</div>`;
        htmlString += `<div>Total Length: ${(responseData.total_length_m / 1000).toFixed(2)} km</div>`;
        htmlString += `<div>Total Signs: ${responseData.total_signs}</div>`;
        htmlString += `</div>`;
    }

    if (responseData.sections && Array.isArray(responseData.sections)) {
        htmlString += `<h4 style="margin: 15px 0 10px 0; color: #374151;">Section Details:</h4>`;
        responseData.sections.forEach(section => {
            htmlString += `<div style="border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px; margin-bottom: 8px; background: white;">`;
            htmlString += `<div style="font-weight: bold; color: #1f2937; margin-bottom: 5px;">${section.name}</div>`;
            htmlString += `<div style="font-size: 12px; color: #6b7280;">Length: ${(section.length_m / 1000).toFixed(2)} km | Chainage: ${section.chainage}</div>`;
            if (section.signs && Object.keys(section.signs).length > 0) {
                const signsList = Object.entries(section.signs).map(([type, count]) => `${type}: ${count}`).join(', ');
                htmlString += `<div style="margin-top: 8px; font-size: 12px;"><strong>Signs:</strong> ${signsList}</div>`;
            }
            htmlString += `</div>`;
        });
    }

    typeContent(bubble, htmlString);
}

function createPaginationControls(container, currentPage, totalPages, onPageChange) {
    const paginationDiv = document.createElement('div');
    paginationDiv.className = 'pagination-controls';
    paginationDiv.style.cssText = `
        display: flex; align-items: center; justify-content: center; gap: 8px;
        margin-top: 12px; padding: 8px; background: #f8fafc;
        border-radius: 6px; border-top: 1px solid #e5e7eb;
    `;
    const prevBtn = document.createElement('button');
    prevBtn.innerHTML = '‹';
    prevBtn.disabled = currentPage === 1;
    prevBtn.style.cssText = `
        width: 28px; height: 28px;
        border: 1px solid ${currentPage === 1 ? '#d1d5db' : '#2563eb'};
        border-radius: 4px; background: ${currentPage === 1 ? '#f9fafb' : 'white'};
        color: ${currentPage === 1 ? '#9ca3af' : '#2563eb'};
        cursor: ${currentPage === 1 ? 'not-allowed' : 'pointer'};
        font-size: 14px; font-weight: bold;
        display: flex; align-items: center; justify-content: center;
    `;
    if (currentPage > 1) {
        prevBtn.addEventListener('click', () => onPageChange(currentPage - 1));
        prevBtn.addEventListener('mouseenter', () => { prevBtn.style.background = '#2563eb'; prevBtn.style.color = 'white'; });
        prevBtn.addEventListener('mouseleave', () => { prevBtn.style.background = 'white'; prevBtn.style.color = '#2563eb'; });
    }
    const pageInfo = document.createElement('span');
    pageInfo.textContent = `${currentPage} / ${totalPages}`;
    pageInfo.style.cssText = `font-size: 12px; color: #6b7280; font-weight: 500; min-width: 40px; text-align: center;`;
    const nextBtn = document.createElement('button');
    nextBtn.innerHTML = '›';
    nextBtn.disabled = currentPage === totalPages;
    nextBtn.style.cssText = `
        width: 28px; height: 28px;
        border: 1px solid ${currentPage === totalPages ? '#d1d5db' : '#2563eb'};
        border-radius: 4px; background: ${currentPage === totalPages ? '#f9fafb' : 'white'};
        color: ${currentPage === totalPages ? '#9ca3af' : '#2563eb'};
        cursor: ${currentPage === totalPages ? 'not-allowed' : 'pointer'};
        font-size: 14px; font-weight: bold;
        display: flex; align-items: center; justify-content: center;
    `;
    if (currentPage < totalPages) {
        nextBtn.addEventListener('click', () => onPageChange(currentPage + 1));
        nextBtn.addEventListener('mouseenter', () => { nextBtn.style.background = '#2563eb'; nextBtn.style.color = 'white'; });
        nextBtn.addEventListener('mouseleave', () => { nextBtn.style.background = 'white'; nextBtn.style.color = '#2563eb'; });
    }
    paginationDiv.appendChild(prevBtn);
    paginationDiv.appendChild(pageInfo);
    paginationDiv.appendChild(nextBtn);
    container.appendChild(paginationDiv);
}

function createButtonSelectionMessage(bubble, responseData) {
    const messageText = document.createElement('div');
    messageText.textContent = responseData.message;
    messageText.style.cssText = 'margin-bottom: 12px;';
    bubble.appendChild(messageText);
    if (responseData.options && responseData.options.length > 0) {
        const totalPages = Math.ceil(responseData.options.length / ITEMS_PER_PAGE);
        const contentContainer = document.createElement('div');
        const renderPage = (page) => {
            contentContainer.innerHTML = '';
            const buttonsContainer = document.createElement('div');
            buttonsContainer.className = 'ro-buttons-container';
            buttonsContainer.style.cssText = 'display: flex; flex-direction: column; gap: 6px;';
            const startIndex = (page - 1) * ITEMS_PER_PAGE;
            const endIndex = Math.min(startIndex + ITEMS_PER_PAGE, responseData.options.length);
            const pageOptions = responseData.options.slice(startIndex, endIndex);
            pageOptions.forEach(option => {
                const button = document.createElement("div");
                button.className = "ro-button";
                button.style.cssText = `
                    display: flex; align-items: flex-start; padding: 10px 12px;
                    border: 1px solid #d1d5db; border-radius: 6px; background: white;
                    cursor: pointer; transition: all 0.2s; font-size: 13px;
                    min-height: 44px; word-break: break-word;
                `;
                button.setAttribute('data-option', option);
                button.innerHTML = `
                    <div class="ro-icon" style="width: 24px; height: 24px; border-radius: 50%; background: #2563eb; color: white; display: flex; align-items: center; justify-content: center; font-weight: bold; margin-right: 8px; font-size: 10px; flex-shrink: 0;">${option.substring(0, 1).toUpperCase()}</div>
                    <div class="ro-content" style="flex: 1; min-width: 0; overflow: hidden;"><div class="ro-title" style="font-weight: 500; color: #1f2937; font-size: 13px; line-height: 1.4; word-wrap: break-word; white-space: normal; overflow-wrap: break-word; display: block;">${option.trim()}</div></div>
                    <div class="ro-arrow" style="color: #6b7280; font-size: 14px; flex-shrink: 0; margin-left: 4px;">›</div>
                `;
                button.addEventListener("mouseenter", () => { button.style.backgroundColor = '#f9fafb'; button.style.borderColor = '#2563eb'; });
                button.addEventListener("mouseleave", () => { button.style.backgroundColor = 'white'; button.style.borderColor = '#d1d5db'; });
                button.addEventListener("click", () => {
                    button.style.backgroundColor = '#2563eb';
                    const titleElement = button.querySelector('.ro-title');
                    const arrowElement = button.querySelector('.ro-arrow');
                    if (titleElement) titleElement.style.color = 'white';
                    if (arrowElement) arrowElement.style.color = 'white';
                    setTimeout(() => sendSelectionMessage(option.trim()), 150);
                });
                buttonsContainer.appendChild(button);
            });
            contentContainer.appendChild(buttonsContainer);
            if (totalPages > 1) {
                createPaginationControls(contentContainer, page, totalPages, renderPage);
            }
            chatBody.scrollTop = chatBody.scrollHeight;
        };
        bubble.appendChild(contentContainer);
        renderPage(1);
    }
}

function createFallbackMessage(bubble, response) {
    let displayText;
    if (typeof response === 'object') {
        displayText = JSON.stringify(response, null, 2);
    } else {
        displayText = String(response);
    }
    // Fallback messages are not typed, they appear instantly.
    bubble.innerHTML = `<pre style="white-space: pre-wrap; font-family: inherit;">${displayText}</pre>`;
}

function parseAndCreateSuggestions(bubbleElement, responseText) {
    const hasDidYouMean = responseText.includes("Did you mean one of these?") || responseText.includes("choose 1, 2");
    if (!hasDidYouMean) return false;
    let suggestionPattern = /(\d+)\.\s*(.+?)(?=\n\d+\.|\nPlease|\n$|$)/gs;
    let matches = [...responseText.matchAll(suggestionPattern)];
    if (matches.length < 2) return false;
    const firstMatchIndex = responseText.indexOf(matches[0][0]);
    let mainMessage = responseText.substring(0, firstMatchIndex).trim();
    
    // Type out the main "Did you mean..." part of the message
    const messageText = document.createElement('div');
    messageText.style.marginBottom = '15px';
    bubbleElement.appendChild(messageText);
    typeContent(messageText, mainMessage);

    // Buttons for suggestions should appear after the main text is typed
    setTimeout(() => {
        const totalPages = Math.ceil(matches.length / ITEMS_PER_PAGE);
        const contentContainer = document.createElement('div');
        const renderSuggestionsPage = (page) => {
            contentContainer.innerHTML = '';
            const suggestionsContainer = document.createElement('div');
            suggestionsContainer.className = 'suggestions-list';
            suggestionsContainer.style.cssText = 'display: flex; flex-direction: column; gap: 6px;';
            const startIndex = (page - 1) * ITEMS_PER_PAGE;
            const endIndex = Math.min(startIndex + ITEMS_PER_PAGE, matches.length);
            const pageMatches = matches.slice(startIndex, endIndex);
            pageMatches.forEach(match => {
                const suggestionItem = document.createElement("div");
                suggestionItem.className = "suggestion-item";
                suggestionItem.style.cssText = `
                    display: flex; align-items: flex-start; padding: 10px; border: 1px solid #d1d5db;
                    border-radius: 4px; background: white; cursor: pointer; transition: background-color 0.2s;
                    font-size: 13px; min-height: 40px; word-break: break-word; animation: slideIn 0.3s ease-out;
                `;
                suggestionItem.innerHTML = `
                    <div class="suggestion-icon" style="width: 20px; height: 20px; border-radius: 50%; background: #f3f4f6; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: bold; margin-right: 8px; flex-shrink: 0; margin-top: 2px; color: #374151;">${match[1]}</div>
                    <div class="suggestion-text" style="flex: 1; line-height: 1.4; word-wrap: break-word; white-space: normal; overflow-wrap: break-word; min-width: 0; color: #1f2937;">${match[2].trim()}</div>
                    <div class="suggestion-arrow" style="color: #6b7280; font-size: 12px; flex-shrink: 0; margin-left: 4px;">›</div>
                `;
                suggestionItem.addEventListener("mouseenter", () => { suggestionItem.style.backgroundColor = '#f9fafb'; });
                suggestionItem.addEventListener("mouseleave", () => { suggestionItem.style.backgroundColor = 'white'; });
                suggestionItem.addEventListener("click", () => sendSelectionMessage(match[2].trim()));
                suggestionsContainer.appendChild(suggestionItem);
            });
            contentContainer.appendChild(suggestionsContainer);
            if (totalPages > 1) {
                createPaginationControls(contentContainer, page, totalPages, renderSuggestionsPage);
            }
        };
        bubbleElement.appendChild(contentContainer);
        renderSuggestionsPage(1);
    }, mainMessage.length * 25); // Delay based on typing speed of main message

    return true;
}

/**
 * UPGRADED: A universal function that "types" out content, whether it's plain text or HTML.
 * It intelligently handles HTML tags, typing only the visible text.
 */
function typeContent(element, content, speed = 25) {
    let visibleText = '';
    let inTag = false;
    // This loop builds a string of only the text that should be visible to the user
    for (const char of content) {
        if (char === '<') inTag = true;
        if (!inTag) visibleText += char;
        if (char === '>') inTag = false;
    }
    
    let visibleIndex = 0;
    let contentIndex = 0;
    
    element.classList.add("typing-cursor");

    const interval = setInterval(() => {
        if (visibleIndex < visibleText.length) {
            let nextChar = content[contentIndex];
            // If the next character is the start of an HTML tag, find the end of it
            if (nextChar === '<') {
                let tagEndIndex = content.indexOf('>', contentIndex);
                // Append the entire tag at once
                element.innerHTML += content.substring(contentIndex, tagEndIndex + 1);
                contentIndex = tagEndIndex;
            } else {
                // Otherwise, it's a visible character, so type it
                element.innerHTML += nextChar;
                visibleIndex++;
            }
            contentIndex++;
            chatBody.scrollTop = chatBody.scrollHeight;
        } else {
            // Ensure any remaining HTML (like closing tags) is rendered
            element.innerHTML = content;
            clearInterval(interval);
            element.classList.remove("typing-cursor");
        }
    }, speed);
}


function showTypingIndicator() {
    if (document.getElementById("typing-indicator")) return;
    const typingDiv = document.createElement("div");
    typingDiv.id = "typing-indicator";
    typingDiv.className = "bot-message";
    typingDiv.innerHTML = `${botAvatarHTML}<div id="typing-text" class="message-bubble">OHS is typing...</div>`;
    chatBody.appendChild(typingDiv);
    chatBody.scrollTop = chatBody.scrollHeight;
}

function hideTypingIndicator() {
    document.getElementById("typing-indicator")?.remove();
}

function showErrorMessage() {
    const errorDiv = document.createElement("div");
    errorDiv.className = "bot-message";
    errorDiv.innerHTML = `${botAvatarHTML}<div class="message-bubble">Sorry, something went wrong. Please try again.</div>`;
    chatBody.appendChild(errorDiv);
    chatBody.scrollTop = chatBody.scrollHeight;
    sendBtn.disabled = false;
}

// --- Event Listeners and Initializers ---

function openChatbot() {
    isChatOpen = true;
    chatbot.style.display = "flex";
    chatBubble.style.display = "none";
    userInput.focus();
    if (isFirstTime) {
        createInitialMessage();
        isFirstTime = false;
    }
}

function closeChatbot() {
    isChatOpen = false;
    chatbot.style.display = "none";
    chatBubble.style.display = "block";
    expandHeader();
}

sendBtn.addEventListener("click", sendMessage);
userInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});
chatIcon.addEventListener("click", () => isChatOpen ? closeChatbot() : openChatbot());
closeChat.addEventListener("click", closeChatbot);
window.addEventListener('load', () => {
    chatbot.style.display = "none";
    chatBubble.style.display = "block";
});

// Add some CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            opacity: 0;
            transform: translateY(10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    .typing-cursor::after {
        content: '|';
        animation: blink 1s infinite;
    }
    
    @keyframes blink {
        0%, 50% { opacity: 1; }
        51%, 100% { opacity: 0; }
    }
`;
document.head.appendChild(style);