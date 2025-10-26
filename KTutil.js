(() => {
  if (window.KTutilLoaded) {
    console.warn("KTutil is already injected on this page.");
    return;
  }
  window.KTutilLoaded = true;

  const existingPanel = document.getElementById("ktutil-panel");
  if (existingPanel) {
    existingPanel.remove();
  }

  const root = document.createElement("div");
  root.id = "ktutil-panel";
  root.style.position = "fixed";
  root.style.top = "16px";
  root.style.right = "16px";
  root.style.width = "260px";
  root.style.maxHeight = "80vh";
  root.style.padding = "12px";
  root.style.zIndex = "999999";
  root.style.borderRadius = "12px";
  root.style.boxShadow = "0 18px 45px rgba(15, 23, 42, 0.35)";
  root.style.background = "rgba(15, 23, 42, 0.92)";
  root.style.color = "#e2e8f0";
  root.style.fontFamily = "'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
  root.style.fontSize = "13px";
  root.style.overflowY = "auto";
  root.style.backdropFilter = "blur(10px)";

  const heading = document.createElement("div");
  heading.textContent = "KTutil";
  heading.style.fontSize = "18px";
  heading.style.fontWeight = "700";
  heading.style.textAlign = "center";
  heading.style.marginBottom = "4px";

  const subheading = document.createElement("div");
  subheading.textContent = "Queue multiple slides and auto-populate.";
  subheading.style.fontSize = "12px";
  subheading.style.opacity = "0.75";
  subheading.style.textAlign = "center";
  subheading.style.marginBottom = "12px";

  const form = document.createElement("form");
  form.style.display = "grid";
  form.style.gap = "12px";

  const slidesContainer = document.createElement("div");
  slidesContainer.style.display = "grid";
  slidesContainer.style.gap = "10px";

  const slideCards = [];

  function createTextField(placeholder = "", multiline = false) {
    const field = multiline ? document.createElement("textarea") : document.createElement("input");
    if (!multiline) {
      field.type = "text";
    }
    field.placeholder = placeholder;
    field.style.width = "100%";
    field.style.boxSizing = "border-box";
    field.style.padding = "8px";
    field.style.borderRadius = "8px";
    field.style.border = "1px solid rgba(148, 163, 184, 0.25)";
    field.style.background = "rgba(15, 23, 42, 0.55)";
    field.style.color = "#e2e8f0";
    field.style.resize = "vertical";
    field.style.minHeight = multiline ? "60px" : "";
    field.style.maxHeight = "160px";
    field.style.fontFamily = "inherit";
    field.style.fontSize = "13px";
    field.style.outline = "none";
    field.addEventListener("focus", () => {
      field.style.borderColor = "#38bdf8";
    });
    field.addEventListener("blur", () => {
      field.style.borderColor = "rgba(148, 163, 184, 0.25)";
    });
    return field;
  }

  function createSelect(options) {
    const select = document.createElement("select");
    select.style.width = "100%";
    select.style.padding = "8px";
    select.style.borderRadius = "8px";
    select.style.border = "1px solid rgba(148, 163, 184, 0.25)";
    select.style.background = "rgba(15, 23, 42, 0.55)";
    select.style.color = "#e2e8f0";
    select.style.fontFamily = "inherit";
    select.style.fontSize = "13px";
    select.style.outline = "none";
    options.forEach(({ value, label }) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      select.appendChild(option);
    });
    return select;
  }

  function updateCardOrdering() {
    slideCards.forEach((card, index) => {
      card.setIndex(index);
      card.updateRemoveVisibility(slideCards.length > 1);
    });
  }

  function createSlideCard(initialData = {}) {
    const {
      type = "quiz",
      question = "",
      answers = ["", "", "", ""],
      correctIndex = 0,
      trueFalseCorrect = "true"
    } = initialData;

    const section = document.createElement("section");
    section.style.display = "grid";
    section.style.gap = "8px";
    section.style.padding = "10px";
    section.style.borderRadius = "10px";
    section.style.background = "rgba(30, 41, 59, 0.55)";
    section.style.border = "1px solid rgba(148, 163, 184, 0.2)";

    const header = document.createElement("div");
    header.style.display = "flex";
    header.style.alignItems = "center";
    header.style.justifyContent = "space-between";

    const title = document.createElement("span");
    title.style.fontWeight = "600";
    title.textContent = "Slide";

    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.textContent = "✕";
    removeButton.title = "Remove slide";
    removeButton.style.border = "none";
    removeButton.style.background = "transparent";
    removeButton.style.color = "#94a3b8";
    removeButton.style.cursor = "pointer";
    removeButton.style.fontSize = "14px";
    removeButton.style.fontWeight = "700";
    removeButton.addEventListener("mouseenter", () => {
      removeButton.style.color = "#f87171";
    });
    removeButton.addEventListener("mouseleave", () => {
      removeButton.style.color = "#94a3b8";
    });
    removeButton.addEventListener("click", () => {
      const index = slideCards.findIndex((card) => card.root === section);
      if (index !== -1) {
        slideCards.splice(index, 1);
        section.remove();
        updateCardOrdering();
      }
    });

    header.appendChild(title);
    header.appendChild(removeButton);

    const typeLabel = document.createElement("label");
    typeLabel.style.display = "grid";
    typeLabel.style.gap = "6px";
    typeLabel.style.fontWeight = "600";
    typeLabel.textContent = "Slide type";

    const typeSelect = createSelect([
      { value: "quiz", label: "Quiz (4 answers)" },
      { value: "truefalse", label: "True / False" }
    ]);
    typeSelect.value = type;

    const questionLabel = document.createElement("label");
    questionLabel.style.display = "grid";
    questionLabel.style.gap = "6px";
    questionLabel.style.fontWeight = "600";
    questionLabel.textContent = "Question";

    const questionField = createTextField("Enter question text", true);
    questionField.value = question;

    const quizGroup = document.createElement("div");
    quizGroup.style.display = "grid";
    quizGroup.style.gap = "6px";

    const answerInputs = Array.from({ length: 4 }).map((_, idx) => {
      const wrapper = document.createElement("label");
      wrapper.style.display = "grid";
      wrapper.style.gap = "4px";
      wrapper.style.fontWeight = "600";
      wrapper.textContent = `Answer ${idx + 1}`;

      const input = createTextField(`Answer option ${idx + 1}`);
      input.value = answers[idx] || "";
      wrapper.appendChild(input);
      quizGroup.appendChild(wrapper);
      return input;
    });

    const correctSelectLabel = document.createElement("label");
    correctSelectLabel.style.display = "grid";
    correctSelectLabel.style.gap = "4px";
    correctSelectLabel.style.fontWeight = "600";
    correctSelectLabel.textContent = "Correct answer";

    const correctSelect = createSelect([
      { value: "0", label: "Option 1" },
      { value: "1", label: "Option 2" },
      { value: "2", label: "Option 3" },
      { value: "3", label: "Option 4" }
    ]);
    correctSelect.value = String(correctIndex);
    correctSelectLabel.appendChild(correctSelect);
    quizGroup.appendChild(correctSelectLabel);

    const trueFalseGroup = document.createElement("div");
    trueFalseGroup.style.display = "grid";
    trueFalseGroup.style.gap = "6px";

    const trueFalseInfo = document.createElement("p");
    trueFalseInfo.textContent = "Correct toggle uses Kahoot's built-in True / False options.";
    trueFalseInfo.style.margin = "0";
    trueFalseInfo.style.fontSize = "11px";
    trueFalseInfo.style.opacity = "0.7";

    const trueFalseSelectLabel = document.createElement("label");
    trueFalseSelectLabel.style.display = "grid";
    trueFalseSelectLabel.style.gap = "4px";
    trueFalseSelectLabel.style.fontWeight = "600";
    trueFalseSelectLabel.textContent = "Correct choice";

    const trueFalseSelect = createSelect([
      { value: "true", label: "True" },
      { value: "false", label: "False" }
    ]);
    trueFalseSelect.value = trueFalseCorrect;
    trueFalseSelectLabel.appendChild(trueFalseSelect);

    trueFalseGroup.appendChild(trueFalseInfo);
    trueFalseGroup.appendChild(trueFalseSelectLabel);

    function syncTypeVisibility() {
      const isQuiz = typeSelect.value === "quiz";
      quizGroup.style.display = isQuiz ? "grid" : "none";
      trueFalseGroup.style.display = isQuiz ? "none" : "grid";
    }

    typeSelect.addEventListener("change", syncTypeVisibility);
    syncTypeVisibility();

    section.appendChild(header);
    typeLabel.appendChild(typeSelect);
    section.appendChild(typeLabel);
    questionLabel.appendChild(questionField);
    section.appendChild(questionLabel);
    section.appendChild(quizGroup);
    section.appendChild(trueFalseGroup);

    return {
      root: section,
      setIndex(index) {
        title.textContent = `Slide ${index + 1}`;
      },
      updateRemoveVisibility(canRemove) {
        removeButton.style.visibility = canRemove ? "visible" : "hidden";
      },
      getData() {
        return {
          type: typeSelect.value,
          question: questionField.value,
          answers: answerInputs.map((input) => input.value),
          correctIndex: parseInt(correctSelect.value, 10) || 0,
          trueFalseCorrect: trueFalseSelect.value
        };
      }
    };
  }

  function addSlide(initialData) {
    const card = createSlideCard(initialData);
    slideCards.push(card);
    slidesContainer.appendChild(card.root);
    updateCardOrdering();
  }

  const addSlideButton = document.createElement("button");
  addSlideButton.type = "button";
  addSlideButton.textContent = "+ Add slide";
  addSlideButton.style.padding = "8px";
  addSlideButton.style.borderRadius = "8px";
  addSlideButton.style.border = "1px solid rgba(148, 163, 184, 0.3)";
  addSlideButton.style.background = "rgba(30, 41, 59, 0.6)";
  addSlideButton.style.color = "#38bdf8";
  addSlideButton.style.fontWeight = "600";
  addSlideButton.style.cursor = "pointer";
  addSlideButton.addEventListener("mouseenter", () => {
    addSlideButton.style.background = "rgba(51, 65, 85, 0.7)";
  });
  addSlideButton.addEventListener("mouseleave", () => {
    addSlideButton.style.background = "rgba(30, 41, 59, 0.6)";
  });
  addSlideButton.addEventListener("click", () => addSlide());

  const controls = document.createElement("div");
  controls.style.display = "grid";
  controls.style.gridTemplateColumns = "1fr 1fr";
  controls.style.gap = "8px";

  const startButton = document.createElement("button");
  startButton.type = "submit";
  startButton.textContent = "Start";
  startButton.style.padding = "9px";
  startButton.style.border = "none";
  startButton.style.borderRadius = "8px";
  startButton.style.fontWeight = "700";
  startButton.style.cursor = "pointer";
  startButton.style.background = "linear-gradient(135deg, #38bdf8, #0ea5e9)";
  startButton.style.color = "#0f172a";
  startButton.style.transition = "transform 0.15s ease";
  startButton.addEventListener("mouseenter", () => {
    startButton.style.transform = "translateY(-1px)";
  });
  startButton.addEventListener("mouseleave", () => {
    startButton.style.transform = "translateY(0)";
  });

  const closeButton = document.createElement("button");
  closeButton.type = "button";
  closeButton.textContent = "Close";
  closeButton.style.padding = "9px";
  closeButton.style.border = "none";
  closeButton.style.borderRadius = "8px";
  closeButton.style.fontWeight = "600";
  closeButton.style.cursor = "pointer";
  closeButton.style.background = "rgba(148, 163, 184, 0.2)";
  closeButton.style.color = "#f8fafc";
  closeButton.addEventListener("click", () => {
    root.remove();
    window.KTutilLoaded = false;
  });

  controls.appendChild(startButton);
  controls.appendChild(closeButton);

  const status = document.createElement("div");
  status.style.fontSize = "11px";
  status.style.opacity = "0.75";
  status.style.minHeight = "14px";

  form.appendChild(slidesContainer);
  form.appendChild(addSlideButton);
  form.appendChild(controls);
  form.appendChild(status);

  function delay(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function waitForCondition(checkFn, timeout = 5000) {
    const start = Date.now();
    return new Promise((resolve, reject) => {
      function check() {
        const result = checkFn();
        if (result) {
          resolve(result);
          return;
        }
        if (Date.now() - start >= timeout) {
          reject(new Error("Timeout waiting for condition."));
          return;
        }
        if (typeof requestAnimationFrame === "function") {
          requestAnimationFrame(check);
        } else {
          setTimeout(check, 50);
        }
      }
      check();
    });
  }

  function waitForElement(selector, timeout = 5000) {
    return waitForCondition(() => document.querySelector(selector), timeout);
  }

  function getActiveQuestionEditor() {
    const editors = Array.from(
      document.querySelectorAll('[data-functional-selector="question-title__input"]')
    );
    return (
      editors.find((el) => el.offsetParent !== null) || editors[editors.length - 1] || null
    );
  }

  function getAnswerEditors() {
    return Array.from(
      document.querySelectorAll('[data-functional-selector="question-answer__input"]')
    );
  }

  function getToggleButtons() {
    return Array.from(
      document.querySelectorAll('[data-functional-selector="question-answer__toggle-button"]')
    );
  }

  function setContentEditableValue(element, value) {
    if (!element) return;

    element.focus();
    document.execCommand("selectAll", false, null);
    document.execCommand("insertText", false, value);

    try {
      element.dispatchEvent(
        new InputEvent("input", {
          data: value,
          inputType: "insertFromPaste",
          bubbles: true,
          cancelable: true
        })
      );
    } catch (error) {
      element.dispatchEvent(new Event("input", { bubbles: true }));
    }

    element.dispatchEvent(new Event("change", { bubbles: true }));
    element.blur();
  }

  function detectCurrentSlideType() {
    const editors = getAnswerEditors();
    if (editors.length === 2) {
      const first = editors[0];
      if (first && first.getAttribute("contenteditable") === "false") {
        return "truefalse";
      }
    }
    return "quiz";
  }

  async function ensureSlideType(type) {
    const currentType = detectCurrentSlideType();
    if (currentType === type) {
      return true;
    }
    return createNewSlide(type);
  }

  async function createNewSlide(type) {
    const addTrigger = document.querySelector(".button__Button-sc-c6mvr2-0");
    if (!addTrigger) {
      console.error("KTutil: Unable to find the add-question button (.button__Button-sc-c6mvr2-0)");
      return false;
    }

    addTrigger.click();
    await delay(200);

    let section;
    try {
      section = await waitForElement(
        "section.create-block__Section-sc-1rs5jsh-2:nth-child(1)",
        4000
      );
    } catch (error) {
      console.error("KTutil: Unable to locate the create-question menu section.");
      return false;
    }

    const optionsWrapper = section.querySelector("div:nth-child(2)");
    if (!optionsWrapper) {
      console.error("KTutil: Create-question menu options wrapper missing.");
      return false;
    }

    const buttons = optionsWrapper.querySelectorAll("button");
    const targetIndex = type === "truefalse" ? 1 : 0;
    const targetButton = buttons[targetIndex];
    if (!targetButton) {
      console.error("KTutil: Could not find the requested question type button.");
      return false;
    }

    targetButton.click();
    await delay(400);
    return true;
  }

  async function fillQuizSlide(data) {
    let questionEditor;
    try {
      questionEditor = await waitForCondition(() => getActiveQuestionEditor(), 4000);
    } catch (error) {
      console.error("KTutil: Question editor not found for quiz slide.");
    }

    if (questionEditor) {
      setContentEditableValue(questionEditor, data.question || "");
    }

    let answerEditors = [];
    try {
      answerEditors = await waitForCondition(() => {
        const editors = getAnswerEditors().filter(
          (editor) => editor.getAttribute("contenteditable") !== "false"
        );
        return editors.length >= 4 ? editors : null;
      }, 4000);
    } catch (error) {
      console.error("KTutil: Quiz answer editors not found.");
    }

    answerEditors.slice(0, 4).forEach((editor, index) => {
      setContentEditableValue(editor, data.answers[index] || "");
    });

    let toggleButtons = [];
    try {
      toggleButtons = await waitForCondition(() => {
        const toggles = getToggleButtons();
        return toggles.length >= 4 ? toggles : null;
      }, 4000);
    } catch (error) {
      console.error("KTutil: Quiz answer toggle buttons not found.");
    }

    const targetToggle = toggleButtons[data.correctIndex];
    if (targetToggle && targetToggle.getAttribute("aria-checked") !== "true") {
      targetToggle.click();
    }
  }

  async function fillTrueFalseSlide(data) {
    let questionEditor;
    try {
      questionEditor = await waitForCondition(() => getActiveQuestionEditor(), 4000);
    } catch (error) {
      console.error("KTutil: Question editor not found for true/false slide.");
    }

    if (questionEditor) {
      setContentEditableValue(questionEditor, data.question || "");
    }

    let toggleButtons = [];
    try {
      toggleButtons = await waitForCondition(() => {
        const toggles = getToggleButtons();
        return toggles.length >= 2 ? toggles : null;
      }, 4000);
    } catch (error) {
      console.error("KTutil: True/False toggle buttons not found.");
    }

    const targetIndex = data.trueFalseCorrect === "false" ? 1 : 0;
    const targetToggle = toggleButtons[targetIndex];
    if (targetToggle && targetToggle.getAttribute("aria-checked") !== "true") {
      targetToggle.click();
    }
  }

  async function fillSlide(data) {
    if (data.type === "truefalse") {
      await fillTrueFalseSlide(data);
    } else {
      await fillQuizSlide(data);
    }
  }

  async function runAutomation(slidesData) {
    for (let index = 0; index < slidesData.length; index += 1) {
      const slideData = slidesData[index];
      status.textContent = `Automating slide ${index + 1} of ${slidesData.length}...`;
      if (index === 0) {
        const ensured = await ensureSlideType(slideData.type);
        if (!ensured) {
          status.textContent = "Failed to prepare the first slide.";
          return;
        }
        await delay(200);
        if (detectCurrentSlideType() !== slideData.type) {
          console.warn(
            "KTutil: Current slide type still differs from the requested type; attempting to continue."
          );
        }
      } else {
        const created = await createNewSlide(slideData.type);
        if (!created) {
          status.textContent = "Failed to create a new slide.";
          return;
        }
      }

      await delay(300);
      await fillSlide(slideData);
      await delay(250);
    }
    status.textContent = "Slides populated.";
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (slideCards.length === 0) {
      status.textContent = "Add at least one slide.";
      return;
    }

    const slidesData = slideCards.map((card) => card.getData());

    startButton.disabled = true;
    startButton.textContent = "Running";
    status.textContent = "Preparing...";

    runAutomation(slidesData)
      .catch((error) => {
        console.error("KTutil:", error);
        status.textContent = "Automation failed. Check the console.";
      })
      .finally(() => {
        startButton.disabled = false;
        startButton.textContent = "Start";
      });
  });

  addSlide();

  root.appendChild(heading);
  root.appendChild(subheading);
  root.appendChild(form);
  document.body.appendChild(root);
})();
