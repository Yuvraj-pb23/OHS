  const chatBtn = document.getElementById('chatBtn');
  const chatWindow = document.getElementById('chatWindow');
  const chatMessages = document.getElementById('chatMessages');
  const userInput = document.getElementById('userInput');
  const sendBtn = document.getElementById('sendBtn');
  let qaData = [];
  let fuse;
  function appendMessage(text, sender='bot') {
    const div = document.createElement('div');
    div.classList.add('message');
    div.classList.add(sender === 'bot' ? 'bot-message' : 'user-message');
    div.textContent = text;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }
  function appendBotMessage(text) {
    appendMessage(text, 'bot');
  }
  function appendUserMessage(text) {
    appendMessage(text, 'user');
  }
  function createSuggestionButtons(suggestions) {
    const container = document.createElement('div');
    container.style.display = 'flex';
    container.style.flexDirection = 'column';
    container.style.margin = '8px 0';
    const label = document.createElement('p');
    label.textContent = "Suggested Questions ? Click to choose:";
    label.style.marginBottom = '8px';
    container.appendChild(label);
    suggestions.forEach(({ item }) => {
      const btn = document.createElement('button');
      btn.textContent = item.question;
      btn.style.margin = '4px 0';
      btn.style.padding = '6px 10px';
      btn.style.borderRadius = '6px';
      btn.style.border = 'none';
      btn.style.background = '#e1f0ff';
      btn.style.cursor = 'pointer';
      btn.style.textAlign = 'left';
      btn.onclick = () => {
        appendUserMessage(btn.textContent);
        appendBotMessage(item.answer);
        container.remove();
      }
      container.appendChild(btn);
    });
    chatMessages.appendChild(container);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }
  function wordsMatch(question, query) {
  const qWords = question.toLowerCase().split(/\W+/).filter(Boolean);
  const inputWords = query.toLowerCase().split(/\W+/).filter(Boolean);
  // Check if all words in question appear in input OR vice versa
  const allInInput = qWords.every(w => inputWords.includes(w));
  const allInQuestion = inputWords.every(w => qWords.includes(w));
  return allInInput || allInQuestion;
}

function exactQuestionMatch(query) {
  for (const {question, answer} of qaData) {
    if (wordsMatch(question, query)) {
      return answer;
    }
  }
  return null;
}

  function findAnswer(query) {
    if (!fuse) return null;
    const exactMatch = exactQuestionMatch(query);
    const results = fuse.search(query, { limit: 5 });
    if (exactMatch) {
      return { type: 'answer', text: exactMatch, showSuggestions: true, suggestions: results };
    }
    if (results.length === 0) {
      return null;
    }
    const bestScore = 1 - results[0].score;
    const threshold = 0.7;
    if (bestScore >= threshold) {
      return { type: 'answer', text: results.item.answer, showSuggestions: true, suggestions: results };
    }
    return { type: 'suggestions', items: results };
  }
  async function loadQA() {
    try {
    const res = await fetch("posh_qa.json");

      qaData = await res.json();
      fuse = new Fuse(qaData, {
        keys: ['question'],
        threshold: 0.4,
        ignoreLocation: true,
        minMatchCharLength: 3,
      });
      appendBotMessage("Hello! I'm your POSH chatbot. Ask me anything about POSH or OHS services.");
    } catch (err) {
      appendBotMessage("Failed to load data, please try later.");
      console.error(err);
    }
  }
  function clearSuggestions() {
    const suggestions = chatMessages.querySelectorAll('button');
    suggestions.forEach(btn => btn.remove());
  }
  function handleInput() {
    clearSuggestions();
    const query = userInput.value.trim();
    if (!query) return;
    appendUserMessage(query);
    userInput.value = '';
    const res = findAnswer(query);
    if (!res) {
      appendBotMessage("Sorry, I couldn't find a relevant answer. Could you please try again?");
      return;
    }
    if (res.type === 'answer') {
      appendBotMessage(res.text);
      if(res.showSuggestions && res.suggestions.length > 1){
        // exclude first as it is already answered
        createSuggestionButtons(res.suggestions.slice(1));
      }
    }
    if (res.type === 'suggestions') {
      appendBotMessage("I found some related questions, please select one:");
      createSuggestionButtons(res.items);
    }
  }
  chatBtn.addEventListener('click', () => {
    if (chatWindow.style.display === 'flex') {
      chatWindow.style.display = 'none';
      clearSuggestions();
    } else {
      chatWindow.style.display = 'flex';
      userInput.focus();
      if (qaData.length === 0) {
        appendBotMessage("Loading knowledge base...");
        loadQA();
      } else {
        appendBotMessage("Hi! How can I assist you today?");
      }
    }
  });
  sendBtn.addEventListener('click', handleInput);
  userInput.addEventListener('keydown', e => {
    if (e.key === 'Enter'){
      e.preventDefault();
      handleInput();
    }
  });

  