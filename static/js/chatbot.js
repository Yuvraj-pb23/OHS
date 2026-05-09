const chatIcon = document.getElementById("chat-icon");
const chatBubble = document.getElementById("chat-bubble");
const chatbot = document.getElementById("chatbot");
const closeChat = document.getElementById("close-chat");
const sendBtn = document.getElementById("send-btn");
const userInput = document.getElementById("user-input");
const chatBody = document.getElementById("chat-body");
const fixedActionsContainer = document.getElementById("fixed-actions");

chatBody.style.overflowY = 'auto';

const chatHeader = document.querySelector(".chat-header");
const resizeChatBtn = document.getElementById("resize-chat");

let isChatOpen = false;
let isFirstTime = true;
let activeTypingInterval = null;

// --- GLOBAL VARIABLES FOR SEQUENCE LOGIC ---
let currentSequenceIndex = 0;
let sequenceData = [];
let docTypingInterval = null;
// -------------------------------------------

const ITEMS_PER_PAGE = 5;

const botAvatarHTML = `
  <div class="message-avatar" style="width: 30px; height: 30px; border-radius: 50%; background: white; padding: 0; display: flex; align-items: center; justify-content: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden;">
    <img src="/static/images/logo_v2.webp" alt="Bot Logo" style="width: 100%; height: 100%; object-fit: cover;">
  </div>
`;

function createInitialMessage() {
    if (chatBody.children.length === 0) {
        const dateSeparator = document.createElement("div");
        dateSeparator.className = "date-separator";
        dateSeparator.textContent = "Today";
        chatBody.appendChild(dateSeparator);
    }

    const botMsgDiv = document.createElement("div");
    botMsgDiv.className = "bot-message";

    botMsgDiv.innerHTML = `
      ${botAvatarHTML}
      <div class="message-bubble welcome-message">
        <p>Welcome to OHPL AI! 
        <br>How can I assist you with POSH, POSCO, Internal Committee matters, or workplace mental health today?
        </p>
      </div>
    `;

    chatBody.appendChild(botMsgDiv);
    chatBody.scrollTop = chatBody.scrollHeight;
}

// --- Opens Modal instead of Chat Message ---
function setupFixedActionButtons() {
    if (!fixedActionsContainer) return;

    fixedActionsContainer.innerHTML = '';
    fixedActionsContainer.style.display = 'flex';

    // Add IRC buttons and IC button
    const topics = ["POSH", "POSCO", "MENTAL HEALTH", "IC"];

    topics.forEach(topic => {
        const button = document.createElement("button");
        button.className = "quick-topic-btn";
        button.textContent = topic;

        button.addEventListener('click', () => {
            fetchAndShowIRCModal(topic);
        });

        fixedActionsContainer.appendChild(button);
    });

}

// ============================================================
// MAIN FUNCTION: MODAL & VIDEO SEQUENCE LOGIC
// ============================================================
function fetchAndShowIRCModal(topic) {
    const modal = document.getElementById('imageModal');
    const modalContainer = modal.querySelector('.image-modal-container');

    // Open modal immediately with loading state
    modal.style.display = "flex";
    setTimeout(() => modal.classList.add('show'), 10);

    modalContainer.innerHTML = `
        <div style="display:flex; height:100%; align-items:center; justify-content:center; color:#666; font-size:18px;">
            <div>Loading ${topic}...</div>
        </div>
    `;

    fetch("/chat/chat/", {
        method: "POST",
        headers: { 
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({ message: topic })
    })
        .then(response => response.json())
        .then(data => {
            const responseData = data.response;

            // ============================================================
            // 2. HANDLE STANDARD IRC IMAGES AND QUESTIONS (ACCORDION UI)
            // ============================================================
            modalContainer.innerHTML = `
            <div class="image-modal-main-content">
                <div class="image-modal-text-area" id="modalLeftText"></div>
                <div id="image-modal-caption"></div>
            </div>
            `;

            const newModalLeftText = document.getElementById('modalLeftText');
            const newCaptionContainer = document.getElementById('image-modal-caption');

            const allImages = responseData.images || [];

            // Initial Left Panel Content
            if (allImages.length > 0) {
                // ... (Keep existing image logic if needed) ...
                const imgData = allImages[0];
                newModalLeftText.innerHTML = `
                    <h3>${imgData.name || 'IRC Standard'}</h3>
                    <span class="fig-num">Figure: ${imgData.fig_number || 'N/A'}</span>
                    <p>${imgData.definition || "No detailed text description available."}</p>
                 `;
            } else {
                newModalLeftText.innerHTML = `<h3>${topic}</h3><p>${responseData.message || "Select a category to view questions."}</p>`;
            }


            // --- RENDER OPTIONS (DRILL-DOWN STYLE) ---
            const renderDrillDownOptions = (options, titleText, isSubView = false) => {
                newCaptionContainer.innerHTML = '';

                const headerContainer = document.createElement('div');
                headerContainer.style.cssText = "display: flex; align-items: center; border-bottom: 1px solid #e2e8f0; padding-bottom: 10px; margin-bottom: 10px;";

                if (isSubView) {
                    const backBtn = document.createElement('button');
                    backBtn.innerHTML = '←';
                    backBtn.style.cssText = "border: none; background: transparent; font-size: 18px; color: #64748b; cursor: pointer; margin-right: 10px; padding: 0 5px;";
                    backBtn.addEventListener('click', () => {
                        // Back to Main Topics
                        renderDrillDownOptions(responseData.options, topic);
                        // Clear Left Panel or Reset to Topic Info?
                        // Ideally reset Left Panel to initial Topic Info
                        if (allImages.length > 0) {
                            // ... existing image reset logic if needed ...
                        } else {
                            newModalLeftText.innerHTML = `<h3>${topic}</h3><p>${responseData.message || "Select a category to view questions."}</p>`;
                        }
                    });
                    headerContainer.appendChild(backBtn);
                }

                const title = document.createElement('h3');
                title.textContent = titleText || topic;
                title.style.cssText = "font-size: 16px; color: #1e293b; margin: 0; flex: 1;";
                headerContainer.appendChild(title);

                newCaptionContainer.appendChild(headerContainer);

                const listContainer = document.createElement('div');
                listContainer.style.cssText = `
                    display: flex; flex-direction: column; gap: 8px; overflow-y: auto; flex: 1; height: 100%;
                `;

                options.forEach((option, index) => {
                    const itemWrapper = document.createElement('div');
                    itemWrapper.className = 'topic-item';
                    itemWrapper.style.cssText = `
                        display: flex; align-items: center; padding: 12px; border: 1px solid #e2e8f0; border-radius: 6px; background: white; cursor: pointer; transition: background 0.2s;
                    `;

                    itemWrapper.innerHTML = `
                         <div style="width:24px; height:24px; background:#2563eb; color:white; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:12px; margin-right:10px;">${index + 1}</div>
                         <div style="font-weight:600; font-size:16px; color:#1f2937; flex:1;">${option}</div>
                         <div style="color:#94a3b8; font-size:18px;">›</div>
                    `;

                    itemWrapper.addEventListener('mouseenter', () => itemWrapper.style.background = '#f1f5f9');
                    itemWrapper.addEventListener('mouseleave', () => itemWrapper.style.background = 'white');

                    // Drill Down Logic
                    itemWrapper.addEventListener('click', () => {
                        fetchQuestionsAndRenderView(option);
                    });

                    listContainer.appendChild(itemWrapper);
                });

                newCaptionContainer.appendChild(listContainer);
            };

            // --- FUNCTION: FETCH & RENDER QUESTION VIEW ---
            const fetchQuestionsAndRenderView = (subtopic) => {
                // Show loading state in Right Panel
                newCaptionContainer.innerHTML = `<div style="padding:20px; text-align:center; color:#666;">Loading questions for ${subtopic}...</div>`;

                fetch("/chat/chat/", {
                    method: "POST",
                    headers: { 
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken()
                    },
                    body: JSON.stringify({ message: subtopic })
                })
                    .then(res => res.json())
                    .then(data => {
                        const ans = data.response;
                        if (ans.type === 'questions_list' && ans.options) {
                            // Render the "Question View" using the same logic helper
                            // But we need to define specific click behavior for questions vs topics
                            renderQuestionListView(subtopic, ans.options);
                        } else {
                            renderDrillDownOptions([], subtopic + " (No questions found)", true);
                        }
                    })
                    .catch(err => {
                        newCaptionContainer.innerHTML = `<div style="color:red; padding:20px;">Error loading questions.</div>`;
                    });
            };

            const renderQuestionListView = (subtopicTitle, questions) => {
                newCaptionContainer.innerHTML = '';

                // Header with Back Button
                const headerContainer = document.createElement('div');
                headerContainer.style.cssText = "display: flex; align-items: center; border-bottom: 1px solid #e2e8f0; padding-bottom: 10px; margin-bottom: 10px;";

                const backBtn = document.createElement('button');
                backBtn.innerHTML = '←';
                backBtn.style.cssText = "border: none; background: transparent; font-size: 18px; color: #64748b; cursor: pointer; margin-right: 10px; padding: 0 5px;";
                backBtn.addEventListener('click', () => {
                    // Go back to Topic List
                    renderDrillDownOptions(responseData.options, topic);
                    // Optional: Reset Left Panel logic
                });
                headerContainer.appendChild(backBtn);

                const title = document.createElement('h3');
                title.textContent = subtopicTitle;
                title.style.cssText = "font-size: 16px; color: #1e293b; margin: 0; flex: 1;";
                headerContainer.appendChild(title);

                newCaptionContainer.appendChild(headerContainer);

                // Question List
                const listContainer = document.createElement('div');
                listContainer.style.cssText = `
                    display: flex; flex-direction: column; gap: 8px; overflow-y: auto; flex: 1; height: 100%;
                `;

                questions.forEach(q => {
                    const qDiv = document.createElement('div');
                    qDiv.textContent = q;
                    qDiv.style.cssText = `
                        padding: 12px; color: #475569; font-size: 15px; cursor: pointer; border-bottom: 1px dashed #cbd5e1;
                        background: white; border-radius: 4px;
                    `;
                    qDiv.addEventListener('mouseenter', () => { qDiv.style.color = '#2563eb'; qDiv.style.background = '#f8fafc'; });
                    qDiv.addEventListener('mouseleave', () => {
                        // Check if active before resetting
                        if (qDiv.getAttribute('data-active') !== 'true') {
                            qDiv.style.color = '#475569'; qDiv.style.background = 'white';
                        }
                    });

                    qDiv.addEventListener('click', () => {
                        // Reset all active
                        listContainer.querySelectorAll('div').forEach(el => {
                            el.style.fontWeight = 'normal';
                            el.style.color = '#475569';
                            el.style.background = 'white';
                            el.setAttribute('data-active', 'false');
                        });
                        // Set active
                        qDiv.style.fontWeight = 'bold';
                        qDiv.style.color = '#2563eb';
                        qDiv.style.background = '#e0f2fe';
                        qDiv.setAttribute('data-active', 'true');

                        fetchAnswerForQuestion(q);
                    });

                    listContainer.appendChild(qDiv);
                });
                newCaptionContainer.appendChild(listContainer);
            };


            // fetchQuestionsForSubtopic REMOVED in favor of fetchQuestionsAndRenderView


            // --- FUNCTION: FETCH ANSWER (Restored) ---
            const fetchAnswerForQuestion = (question) => {
                const leftPanel = document.getElementById('modalLeftText');

                // Show loading
                if (activeTypingInterval) clearInterval(activeTypingInterval);
                leftPanel.innerHTML = `
                    <h3 style="color:#2563eb;">${question}</h3>
                    <div style="margin-top:20px; color:#666;">Loading answer...</div>
                `;

                fetch("/chat/chat/", {
                    method: "POST",
                    headers: { 
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken()
                    },
                    body: JSON.stringify({ message: question })
                })
                    .then(res => res.json())
                    .then(data => {
                        const ans = data.response;
                        let answerText = "";

                        if (ans.type === 'answer') {
                            answerText = ans.message;
                        } else {
                            answerText = typeof ans === 'string' ? ans : JSON.stringify(ans);
                        }

                        leftPanel.innerHTML = `<h3 style="color:#2563eb;">Q: ${question}</h3>`;
                        const answerDiv = document.createElement('div');
                        answerDiv.style.cssText = "margin-top:15px; line-height:1.6; color:#334155; white-space: pre-wrap; font-size: 1.1rem;";
                        leftPanel.appendChild(answerDiv);

                        activeTypingInterval = typeContent(answerDiv, answerText, 15);
                    })
                    .catch(err => {
                        leftPanel.innerHTML += `<div style="color:red;">Failed to load answer.</div>`;
                    });
            };


            // Initial logic start
            if (responseData.options && responseData.options.length > 0) {
                renderDrillDownOptions(responseData.options, topic);
            } else {
                newCaptionContainer.innerHTML = `<p>${responseData.message || 'No data.'}</p>`;
            }

        })
        .catch(error => {
            console.error("Modal Fetch Error:", error);
            modalContainer.innerHTML = `
            <div style="padding: 40px; text-align: center;">
                <div style="color:red; font-size: 18px; margin-bottom: 10px;">Error loading content</div>
                <div style="color:#666;">${error.message}</div>
            </div>
        `;
        });
}


function sendMessage() {
    const message = userInput.value.trim();
    if (message === "" || sendBtn.disabled) return;

    sendBtn.disabled = true;
    appendUserMessage(message);
    userInput.value = "";
    showTypingIndicator();
    fetchBotResponse(message);
}

function sendSelectionMessage(selectionText) {
    if (!isChatOpen) openChatbot();
    appendUserMessage(selectionText);
    showTypingIndicator();
    fetchBotResponse(selectionText);
}

function fetchBotResponse(message) {
    fetch("/chat/chat/", {
        method: "POST",
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
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
            handleBotResponse(data, message);
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

function handleBotResponse(data, originalMessage = '') {
    const responseData = data.response;
    const images = responseData.images;
    const shouldReset = data.reset || false;

    if (shouldReset) {
        const botMsgDiv = document.createElement("div");
        botMsgDiv.className = "bot-message";
        botMsgDiv.innerHTML = `${botAvatarHTML}<div class="message-bubble">${responseData}</div>`;
        chatBody.appendChild(botMsgDiv);
        setTimeout(() => {
            chatBody.innerHTML = '';
            createInitialMessage();
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

    const introText = responseData.message || (typeof responseData === 'string' ? responseData : '');
    const mainTextContainer = document.createElement('div');
    bubble.appendChild(mainTextContainer);

    if (images && Array.isArray(images) && images.length > 0) {
        createImageResultsMessage(mainTextContainer, introText, images, originalMessage);
    } else if (typeof responseData === 'object' && responseData !== null && responseData.display_type) {
        switch (responseData.display_type) {
            case 'text_block':
                createTextBlockMessage(mainTextContainer, responseData);
                break;
            case 'detailed_breakdown':
                createDetailedBreakdownMessage(mainTextContainer, responseData);
                break;
            default:
                typeContent(mainTextContainer, introText);
        }
    } else {
        const responseText = introText;
        if (!parseAndCreateSuggestions(bubble, responseText)) {
            typeContent(mainTextContainer, responseText);
        }
    }

    if (responseData.options && Array.isArray(responseData.options) && responseData.options.length > 0) {
        const introTextLength = introText.length;
        setTimeout(() => {
            const buttonContainer = document.createElement('div');
            buttonContainer.style.marginTop = '15px';
            bubble.appendChild(buttonContainer);

            createButtonSelectionMessage(buttonContainer, responseData);
            chatBody.scrollTop = chatBody.scrollHeight;
        }, introTextLength * 25);
    }

    chatBody.scrollTop = chatBody.scrollHeight;
    sendBtn.disabled = false;
}

function createImageResultsMessage(container, introText, images, searchedFigNumber) {
    function updateModalContent(modalLeftText, captionText, image) {
        if (activeTypingInterval) {
            clearInterval(activeTypingInterval);
        }

        modalLeftText.innerHTML = `
            <h3>${image.name || 'Details'}</h3>
            <span class="fig-num">Figure: ${image.fig_number || 'N/A'}</span>
        `;

        const descDiv = document.createElement('p');
        modalLeftText.appendChild(descDiv);

        const description = image.definition || "No description available.";
        activeTypingInterval = typeContent(descDiv, description, 10);

        captionText.innerHTML = '';
    }

    function buildThumbnailGallery(galleryContainer, modalLeftText, captionText, relatedImages, activeImageUrl) {
        galleryContainer.innerHTML = '';
        relatedImages.forEach(relatedImg => {
            const thumbDiv = document.createElement('div');
            thumbDiv.className = 'thumbnail-item';
            if (relatedImg.image_url === activeImageUrl) {
                thumbDiv.classList.add('active');
            }

            const thumbImg = document.createElement('img');
            thumbImg.src = relatedImg.image_url;
            thumbImg.alt = relatedImg.name;
            thumbDiv.appendChild(thumbImg);

            thumbDiv.addEventListener('click', () => {
                updateModalContent(modalLeftText, captionText, relatedImg);
                galleryContainer.querySelector('.active')?.classList.remove('active');
                thumbDiv.classList.add('active');
            });
            galleryContainer.appendChild(thumbDiv);
        });
    }

    const searchQuery = (searchedFigNumber || '').trim();
    const isExactFigSearch = images.length === 1 ||
        images.some(img => img.fig_number === searchQuery);

    let chatImages = images;

    if (isExactFigSearch && searchQuery) {
        const exactMatchImage = images.find(img => img.fig_number === searchQuery);
        if (exactMatchImage) {
            chatImages = [exactMatchImage];
        }
    }

    const addImagesAfterTyping = () => {
        const imageContainer = document.createElement('div');
        imageContainer.style.cssText = `
            display: grid;
            grid-template-columns: ${chatImages.length === 1 ? '1fr' : '1fr 1fr'};
            gap: 10px;
            margin-top: 10px;
        `;

        const modal = document.getElementById('imageModal');
        const modalLeftText = document.getElementById('modalLeftText');
        const captionText = document.getElementById('image-modal-caption');
        const thumbnailGallery = document.getElementById('thumbnail-gallery');

        chatImages.forEach(image => {
            const card = document.createElement('div');
            card.className = 'image-result-card';
            card.style.cssText = `
                cursor: pointer; border: 1px solid #e5e7eb; border-radius: 8px;
                overflow: hidden; background: white; transition: transform 0.2s, box-shadow 0.2s;
                display: flex; flex-direction: column; height: 100%;
            `;

            card.addEventListener('mouseenter', () => {
                card.style.transform = 'scale(1.05)';
                card.style.boxShadow = '0 4px 12px rgba(0,0,0,0.1)';
            });
            card.addEventListener('mouseleave', () => {
                card.style.transform = 'scale(1)';
                card.style.boxShadow = 'none';
            });

            card.addEventListener('click', () => {
                modal.style.display = "flex";
                setTimeout(() => modal.classList.add('show'), 10);

                updateModalContent(modalLeftText, captionText, image);

                thumbnailGallery.innerHTML = '<div style="color: #6b7280; font-size: 12px; padding: 10px;">Loading related images...</div>';

                fetch("/chat/chat/", {
                    method: "POST",
                    headers: { 
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken()
                    },
                    body: JSON.stringify({ message: image.fig_number })
                })
                    .then(response => response.json())
                    .then(data => {
                        const fullGalleryImages = data.response.images || [];
                        if (fullGalleryImages.length > 0) {
                            buildThumbnailGallery(thumbnailGallery, modalLeftText, captionText, fullGalleryImages, image.image_url);
                        } else {
                            buildThumbnailGallery(thumbnailGallery, modalLeftText, captionText, [image], image.image_url);
                        }
                    })
                    .catch(error => {
                        console.error("Error fetching full image gallery:", error);
                        thumbnailGallery.innerHTML = '<div style="color: #d9534f; font-size: 12px; padding: 10px;">Could not load gallery.</div>';
                    });
            });

            const imageWrapper = document.createElement('div');
            imageWrapper.style.cssText = `width: 100%; height: 120px; overflow: hidden; background: #f3f4f6;`;
            const imgElement = document.createElement('img');
            imgElement.src = image.image_url;
            imgElement.alt = image.name;
            imgElement.style.cssText = `width: 100%; height: 100%; object-fit: cover;`;
            imageWrapper.appendChild(imgElement);

            const detailsDiv = document.createElement('div');
            detailsDiv.style.cssText = `padding: 8px; flex-grow: 1; display: flex; flex-direction: column;`;
            const nameElement = document.createElement('div');
            nameElement.textContent = image.name;
            nameElement.style.cssText = `
                font-weight: 600; color: #1f2937; font-size: 12px; margin-bottom: 4px; line-height: 1.3;
                overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
            `;
            const figElement = document.createElement('div');
            figElement.textContent = `Fig: ${image.fig_number}`;
            figElement.style.cssText = `font-size: 11px; color: #6b7280;`;
            detailsDiv.appendChild(nameElement);
            detailsDiv.appendChild(figElement);

            card.appendChild(imageWrapper);
            card.appendChild(detailsDiv);
            imageContainer.appendChild(card);
        });

        container.appendChild(imageContainer);
        chatBody.scrollTop = chatBody.scrollHeight;
    };

    typeContent(container, introText, 25, addImagesAfterTyping);
}


function createTextBlockMessage(bubble, responseData) {
    let htmlString = '';
    if (responseData.title) {
        htmlString += `<h3 style="margin: 0 0 10px 0; color: #2563eb; font-size: 18px;">${responseData.title}</h3>`;
    }
    if (responseData.lines && Array.isArray(responseData.lines)) {
        responseData.lines.forEach(line => {
            const content = line.trim() === '' ? '<br>' : line;
            htmlString += `<div style="margin-bottom: 4px; line-height: 1.4;">${content}</div>`;
        });
    }
    typeContent(bubble, htmlString);
}

function createDetailedBreakdownMessage(bubble, responseData) {
    let htmlString = '';
    if (responseData.title) {
        htmlString += `<h3 style="margin: 0 0 15px 0; color: #2563eb; font-size: 18px;">${responseData.title}</h3>`;
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
    paginationDiv.style.cssText = `display: flex; align-items: center; justify-content: center; gap: 8px; margin-top: 12px; padding: 8px; background: #f8fafc; border-radius: 6px; border-top: 1px solid #e5e7eb;`;
    const prevBtn = document.createElement('button');
    prevBtn.innerHTML = '‹';
    prevBtn.disabled = currentPage === 1;
    prevBtn.style.cssText = `width: 28px; height: 28px; border: 1px solid ${currentPage === 1 ? '#d1d5db' : '#2563eb'}; border-radius: 4px; background: ${currentPage === 1 ? '#f9fafb' : 'white'}; color: ${currentPage === 1 ? '#9ca3af' : '#2563eb'}; cursor: ${currentPage === 1 ? 'not-allowed' : 'pointer'}; font-size: 14px; font-weight: bold; display: flex; align-items: center; justify-content: center;`;
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
    nextBtn.style.cssText = `width: 28px; height: 28px; border: 1px solid ${currentPage === totalPages ? '#d1d5db' : '#2563eb'}; border-radius: 4px; background: ${currentPage === totalPages ? '#f9fafb' : 'white'}; color: ${currentPage === totalPages ? '#9ca3af' : '#2563eb'}; cursor: ${currentPage === totalPages ? 'not-allowed' : 'pointer'}; font-size: 14px; font-weight: bold; display: flex; align-items: center; justify-content: center;`;
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

function createButtonSelectionMessage(container, responseData) {
    if (responseData.message && responseData.show_message_once) {
        const messageText = document.createElement('div');
        messageText.textContent = responseData.message;
        messageText.style.cssText = 'margin-bottom: 12px; font-weight: 600; color: #1f2937; font-size: 16px;';
        container.appendChild(messageText);
    } else if (responseData.message && !responseData.show_message_once) {
        const messageText = document.createElement('div');
        messageText.textContent = responseData.message;
        messageText.style.cssText = 'margin-bottom: 12px;';
        container.appendChild(messageText);
    }

    if (responseData.options && responseData.options.length > 0) {
        const contentContainer = document.createElement('div');
        const showPagination = responseData.pagination !== false;

        const renderPage = (page) => {
            contentContainer.innerHTML = '';
            const buttonsContainer = document.createElement('div');
            buttonsContainer.style.cssText = 'display: flex; flex-direction: column; gap: 6px; margin-top: 6px;';

            let pageOptions;
            if (showPagination) {
                const startIndex = (page - 1) * ITEMS_PER_PAGE;
                const endIndex = Math.min(startIndex + ITEMS_PER_PAGE, responseData.options.length);
                pageOptions = responseData.options.slice(startIndex, endIndex);
            } else {
                pageOptions = responseData.options;
            }

            pageOptions.forEach((option, index) => {
                const buttonWrapper = document.createElement("div");
                buttonWrapper.style.cssText = `
                    display: flex;
                    align-items: flex-start;
                    padding: 10px 12px;
                    border: 1px solid #d1d5db;
                    border-radius: 6px;
                    background: white;
                    cursor: pointer;
                    transition: background-color 0.2s, border-color 0.2s;
                    font-size: 13px;
                    min-height: 44px;
                    word-break: break-word;
                `;

                const icon = document.createElement('div');
                icon.textContent = option.substring(0, 1).toUpperCase();
                icon.style.cssText = `
                    width: 24px;
                    height: 24px;
                    border-radius: 50%;
                    background: #2563eb;
                    color: white;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-weight: bold;
                    margin-right: 8px;
                    font-size: 10px;
                    flex-shrink: 0;
                `;

                const textWrapper = document.createElement('div');
                textWrapper.style.cssText = `
                    flex: 1;
                    min-width: 0;
                    overflow: hidden;
                `;

                const title = document.createElement('div');
                title.textContent = option.trim();
                title.style.cssText = `
                    font-weight: 500;
                    color: #1f2937;
                    font-size: 15px;
                    line-height: 1.4;
                    word-wrap: break-word;
                    white-space: normal;
                    overflow-wrap: break-word;
                    display: block;
                `;

                const arrow = document.createElement('div');
                arrow.textContent = '›';
                arrow.style.cssText = `
                    color: #6b7280;
                    font-size: 14px;
                    flex-shrink: 0;
                    margin-left: 4px;
                    font-weight: bold;
                `;

                textWrapper.appendChild(title);
                buttonWrapper.appendChild(icon);
                buttonWrapper.appendChild(textWrapper);
                buttonWrapper.appendChild(arrow);

                buttonWrapper.addEventListener('mouseenter', function () {
                    if (!this.dataset.clicked) {
                        this.style.backgroundColor = '#f9fafb';
                        this.style.borderColor = '#2563eb';
                    }
                });

                buttonWrapper.addEventListener('mouseleave', function () {
                    if (!this.dataset.clicked) {
                        this.style.backgroundColor = 'white';
                        this.style.borderColor = '#d1d5db';
                    }
                });

                buttonWrapper.addEventListener('click', function () {
                    this.dataset.clicked = 'true';
                    this.style.backgroundColor = '#2563eb';
                    this.style.borderColor = '#2563eb';
                    icon.style.color = 'white';
                    icon.style.backgroundColor = '#2563eb';
                    title.style.color = 'white';
                    arrow.style.color = 'white';

                    setTimeout(() => {
                        sendSelectionMessage(option.trim());
                    }, 150);
                });

                buttonsContainer.appendChild(buttonWrapper);
            });

            contentContainer.appendChild(buttonsContainer);

            if (showPagination) {
                const totalPages = Math.ceil(responseData.options.length / ITEMS_PER_PAGE);
                if (totalPages > 1) {
                    createPaginationControls(contentContainer, page, totalPages, renderPage);
                }
            }

            chatBody.scrollTop = chatBody.scrollHeight;
        };

        container.appendChild(contentContainer);
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
    const messageText = document.createElement('div');
    messageText.style.marginBottom = '15px';
    bubbleElement.appendChild(messageText);
    typeContent(messageText, mainMessage);
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
                suggestionItem.style.cssText = `display: flex; align-items: flex-start; padding: 10px; border: 1px solid #d1d5db; border-radius: 4px; background: white; cursor: pointer; transition: background-color 0.2s; font-size: 13px; min-height: 40px; word-break: break-word; animation: slideIn 0.3s ease-out;`;
                suggestionItem.innerHTML = `<div class="suggestion-icon" style="width: 20px; height: 20px; border-radius: 50%; background: #f3f4f6; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: bold; margin-right: 8px; flex-shrink: 0; margin-top: 2px; color: #374151;">${match[1]}</div><div class="suggestion-text" style="flex: 1; line-height: 1.4; word-wrap: break-word; white-space: normal; overflow-wrap: break-word; min-width: 0; color: #1f2937;">${match[2].trim()}</div><div class="suggestion-arrow" style="color: #6b7280; font-size: 12px; flex-shrink: 0; margin-left: 4px;">›</div>`;
                suggestionItem.addEventListener("mouseenter", () => { suggestionItem.style.backgroundColor = '#f9fafb'; });
                suggestionItem.addEventListener("mouseleave", () => { suggestionItem.style.backgroundColor = 'white'; });
                suggestionItem.addEventListener("click", () => sendSelectionMessage(match[2].trim()));
                suggestionsContainer.appendChild(suggestionItem);
            });
            contentContainer.appendChild(suggestionsContainer);
            if (totalPages > 1) {
                createPaginationControls(contentContainer, page, totalPages, renderSuggestionsPage);
            }

            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    chatBody.scrollTop = chatBody.scrollHeight;
                });
            });
        };
        bubbleElement.appendChild(contentContainer);
        renderSuggestionsPage(1);
    }, mainMessage.length * 25);
    return true;
}

function typeContent(element, content, speed = 25, callback) {
    let visibleText = '';
    let inTag = false;
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
            if (nextChar === '<') {
                let tagEndIndex = content.indexOf('>', contentIndex);
                element.innerHTML += content.substring(contentIndex, tagEndIndex + 1);
                contentIndex = tagEndIndex;
            } else {
                element.innerHTML += nextChar;
                visibleIndex++;
            }
            contentIndex++;
            chatBody.scrollTop = chatBody.scrollHeight;
        } else {
            element.innerHTML = content;
            clearInterval(interval);
            element.classList.remove("typing-cursor");
            if (callback) {
                callback();
            }
        }
    }, speed);
    return interval;
}

function showTypingIndicator() {
    if (document.getElementById("typing-indicator")) return;
    const typingDiv = document.createElement("div");
    typingDiv.id = "typing-indicator";
    typingDiv.className = "bot-message";
    typingDiv.innerHTML = `${botAvatarHTML}<div id="typing-text" class="message-bubble">OHPL AI is typing...</div>`;
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

function openChatbot() {
    isChatOpen = true;
    chatbot.style.display = "flex";
    // chatBubble.style.display = "none";
    userInput.focus();
    if (isFirstTime) {
        createInitialMessage();
        setupFixedActionButtons();
        isFirstTime = false;
    }
}

function closeChatbot() {
    isChatOpen = false;
    chatbot.style.display = "none";
    // chatBubble.style.display = "block";
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

if (resizeChatBtn) {
    resizeChatBtn.addEventListener("click", () => {
        chatbot.classList.toggle("expanded");
    });
}

window.addEventListener('load', () => {
    if (isFirstTime) {
        createInitialMessage();
        setupFixedActionButtons();
        isFirstTime = false;
    }

    const modal = document.getElementById('imageModal');
    const modalClose = document.querySelector('.image-modal-close');

    const closeModal = () => {
        modal.classList.remove('show');
        setTimeout(() => {
            modal.style.display = "none";

            // --- CLEANUP: Stop intervals and video when closed ---
            if (activeTypingInterval) clearInterval(activeTypingInterval);
            if (docTypingInterval) clearInterval(docTypingInterval);

            const videoPlayer = document.getElementById('concessionVideo');
            if (videoPlayer) {
                videoPlayer.pause();
                videoPlayer.src = "";
            }
            // -----------------------------------------------------
        }, 300);
    };

    modalClose.onclick = closeModal;
    modal.onclick = (event) => {
        if (event.target === modal) {
            closeModal();
        }
    };
});

const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
`;
document.head.appendChild(style);