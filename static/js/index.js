function executeScripts(container) {
    const scripts = Array.from(container.querySelectorAll('script'));
    scripts.forEach(oldScript => {
        const newScript = document.createElement('script');
        for (const {name, value} of Array.from(oldScript.attributes)) {
            newScript.setAttribute(name, value);
        }
        if (!oldScript.src) {
            newScript.textContent = oldScript.textContent;
        }
        oldScript.parentNode.replaceChild(newScript, oldScript);
    });
}

async function loadGallery() {
    const mainContainer = document.getElementById("main-container");
    const mainResp = await fetch("/gallery", {
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    });
    if (!mainResp.ok) {
        throw new Error(`Failed to load gallery: ${mainResp.status}`);
    }
    const mainHtml = await mainResp.text();
    mainContainer.innerHTML = mainHtml;
    mainContainer.style.display = "block";
    executeScripts(mainContainer);
}

async function login() {
    const passwordInput = document.getElementById("password");
    const errorMsg = document.getElementById("error-msg");
    const loginContainer = document.getElementById("login-container");

    const password = passwordInput.value;

    try {
        const response = await fetch("/login", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({password})
        });

        const result = await response.json();
        if (result.success) {
            loginContainer.style.display = "none";
            await loadGallery();
        } else {
            errorMsg.textContent = result.error || "Login failed";
        }

    } catch (err) {
        errorMsg.textContent = "Server error";
        console.error(err);
    }
}

async function checkSessionAndInit() {
    const loginContainer = document.getElementById("login-container");
    const errorMsg = document.getElementById("error-msg");
    try {
        const resp = await fetch('/session', {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        if (!resp.ok) throw new Error(`Session check failed: ${resp.status}`);
        const data = await resp.json();
        if (data.logged_in) {
            if (loginContainer) loginContainer.style.display = 'none';
            await loadGallery();
        } else {
            if (loginContainer) loginContainer.style.display = 'block';
        }
    } catch (e) {
        console.error(e);
        if (errorMsg) errorMsg.textContent = 'Unable to check session status.';
    }
}

const loginBtn = document.getElementById("login-btn");
if (loginBtn) {
    loginBtn.addEventListener("click", login);
}

document.addEventListener('DOMContentLoaded', checkSessionAndInit);

