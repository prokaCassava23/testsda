// ==UserScript==
// @name         CF Legends: Auto-farm Referral
// @namespace    http://tampermonkey.net/
// @version      1.9
// @description  Automates cflegends inviting process with Start/Stop toggle
// @author       Chisato-Chan
// @match        *://*.playcfl.com/*
// @match        *://*.intlgame.com/*
// @run-at       document-start
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        unsafeWindow
// ==/UserScript==

(function() {
    'use strict';

    const CONFIG = {
        BASE_EMAIL: "test",
        EMAIL_DOMAIN: "@gmail.com",
        USE_RANDOM_TAG: true,
        STARTING_INDEX: 1,
        FINAL_TIMEOUT: 30,
        EMAIL_POLL_TIMEOUT: 120,
        SERVER_BASE: "http://localhost:5000"
    };

    const URLS = {
        GET_CODE: `${CONFIG.SERVER_BASE}/get-code`,
        LOG: `${CONFIG.SERVER_BASE}/log-success`,
        ALARM: `${CONFIG.SERVER_BASE}/trigger-alarm`
    };

    let currentCount = GM_getValue("cfl_total_done", 0);
    let limitValue = GM_getValue("cfl_limit_max", 0);
    let savedIndex = GM_getValue("cfl_loop_index", 0);
    let isRunning = GM_getValue("cfl_is_running", false);

    let scriptStep = 0;
    let isPolling = false;
    let regionTimer = 0;
    let emailPollStartTime = 0;
    let wakeLock = null;
    let alarmTriggered = false;

    let emailTag;
    if (CONFIG.USE_RANDOM_TAG) {
        let counter = GM_getValue("email_counter", 0);
        const base = Date.now().toString().slice(-8);
        emailTag = `${base}${counter % 100}`;
        counter++;
        GM_setValue("email_counter", counter);
    } else {
        if (CONFIG.STARTING_INDEX > savedIndex) {
            GM_setValue("cfl_loop_index", CONFIG.STARTING_INDEX);
            savedIndex = CONFIG.STARTING_INDEX;
        }
        emailTag = savedIndex;
    }
    const EMAIL_TO_USE = `${CONFIG.BASE_EMAIL}+${emailTag}${CONFIG.EMAIL_DOMAIN}`;

    const qs = (sel) => document.querySelector(sel);
    const xpath = (path) => {
        try {
            return document.evaluate(path, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
        } catch(e) { return null; }
    };

    let uiBox = null;

    // --- UPDATED APPLE UI STYLES ---
    const APPLE_STYLES = `
        #cfl-status-box {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            position: fixed;
            top: 20px;
            right: 20px;
            width: 240px; /* Compact width */
            background: rgba(30, 30, 30, 0.65);
            backdrop-filter: blur(20px) saturate(180%);
            -webkit-backdrop-filter: blur(20px) saturate(180%);
            border: 1px solid rgba(255, 255, 255, 0.12);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
            border-radius: 14px;
            z-index: 999999;
            color: #fff;
            padding: 12px;
            transition: all 0.3s ease;
            user-select: none;
        }
        .cfl-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            padding-bottom: 8px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }
        .cfl-title { font-weight: 600; font-size: 12px; color: #fff; letter-spacing: -0.02em; }
        .cfl-count { font-weight: 700; font-size: 12px; color: #0a84ff; background: rgba(10, 132, 255, 0.15); padding: 2px 8px; border-radius: 6px; }

        /* Controls Row */
        .cfl-controls { display: flex; gap: 6px; align-items: center; justify-content: space-between; }

        /* General Button Styles */
        .cfl-btn {
            border: none;
            cursor: pointer;
            font-size: 11px;
            font-weight: 500;
            border-radius: 6px;
            transition: all 0.2s;
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .cfl-btn:active { transform: scale(0.96); }

        /* Start/Stop Button */
        #cfl-btn-toggle {
            flex: 1; /* Takes available space */
            padding: 4px 0;
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .btn-start { background: #30d158; color: #000; box-shadow: 0 2px 8px rgba(48, 209, 88, 0.2); }
        .btn-stop { background: #ff453a; color: #fff; box-shadow: 0 2px 8px rgba(255, 69, 58, 0.2); }

        /* Input Group */
        .input-group {
            display: flex;
            flex: 0 0 auto; /* Do not stretch */
            background: rgba(0,0,0,0.2);
            border-radius: 6px;
            padding: 2px;
            border: 1px solid rgba(255,255,255,0.1);
            align-items: center;
        }

        /* Number Input - VERY COMPACT */
        #cfl-input-limit {
            background: transparent;
            border: none;
            color: white;
            text-align: center;
            font-size: 11px;
            outline: none;
            padding: 2px 0;
            width: 50px; /* Fixed small width */
        }
        /* Hide Spinner Arrows */
        input::-webkit-outer-spin-button, input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
        input[type=number] { -moz-appearance: textfield; }

        /* Icon Buttons (Set/Reset) */
        .btn-icon { background: transparent; color: #888; padding: 4px 10px; font-size: 10px; }
        .btn-icon:hover { color: #fff; background: rgba(255,255,255,0.1); }

        /* Footer Status */
        .cfl-footer { margin-top: 8px; }
        .cfl-status { font-weight: 600; font-size: 10px; text-shadow: 0 0 10px rgba(0,0,0,0.5); text-align: center; opacity: 0.9; }
    `;

    function getUIHTML(msg, color, count, limit) {
        let limitDisplay = limit > 0 ? limit : "∞";
        let btnClass = isRunning ? "btn-stop" : "btn-start";
        let btnText = isRunning ? "STOP" : "START";

        return `
            <div class="cfl-header">
                <span class="cfl-title">CFL Automation</span>
                <span class="cfl-count">${count} / ${limitDisplay}</span>
            </div>

            <div class="cfl-controls">
                <button id="cfl-btn-toggle" class="cfl-btn ${btnClass}">${btnText}</button>
                <div class="input-group">
                    <input type="number" id="cfl-input-limit" value="${limit}" placeholder="∞">
                    <button id="cfl-btn-save" class="cfl-btn btn-icon" title="Save">SET</button>
                    <button id="cfl-btn-reset" class="cfl-btn btn-icon" title="Reset">↻</button>
                </div>
            </div>

            <div class="cfl-footer">
                <div class="cfl-status" style="color:${color}">${isRunning ? msg : "⏸️ Paused"}</div>
            </div>
        `;
    }

    function ensureUI() {
        if (!document.body) return;

        if (!document.getElementById('cfl-custom-styles')) {
            const styleSheet = document.createElement("style");
            styleSheet.id = 'cfl-custom-styles';
            styleSheet.innerText = APPLE_STYLES;
            document.head.appendChild(styleSheet);
        }

        if (!document.getElementById('cfl-status-box')) {
            uiBox = document.createElement('div');
            uiBox.id = 'cfl-status-box';
            uiBox.innerHTML = getUIHTML("🚀 Ready...", "#30d158", currentCount, limitValue);
            document.body.appendChild(uiBox);
        }
    }
    setInterval(ensureUI, 500);

    document.addEventListener('click', function(e){
        if(e.target && e.target.id === 'cfl-btn-toggle'){
            isRunning = !isRunning;
            GM_setValue("cfl_is_running", isRunning);
            updateStatus(isRunning ? "RESUMING..." : "PAUSED");
        }
        if(e.target && e.target.id === 'cfl-btn-save'){
            let val = document.getElementById('cfl-input-limit').value;
            GM_setValue("cfl_limit_max", parseInt(val) || 0);
            limitValue = parseInt(val) || 0;
            updateStatus("Limit Updated");
        }
        if(e.target && e.target.id === 'cfl-btn-reset'){
            GM_setValue("cfl_total_done", 0);
            currentCount = 0;
            updateStatus("Counter Reset");
        }
    });

    function updateStatus(msg, color='#30d158') {
        const box = document.getElementById('cfl-status-box');
        if (box) {
            if (!alarmTriggered) {
                 box.style.background = 'rgba(30, 30, 30, 0.65)';
                 box.style.border = '1px solid rgba(255, 255, 255, 0.12)';
            }
            box.innerHTML = getUIHTML(msg, color, currentCount, limitValue);
        }
        console.log(`[CFL BOT] ${msg}`);
    }

    function triggerServerAlarm() {
        if (alarmTriggered) return;
        alarmTriggered = true;
        updateStatus("🚨 CAPTCHA DETECTED! 🚨", "white");

        let toggle = true;
        const box = document.getElementById('cfl-status-box');
        setInterval(() => {
            if(box) {
                if (toggle) {
                    box.style.background = 'rgba(255, 69, 58, 0.8)';
                    box.style.borderColor = 'white';
                } else {
                    box.style.background = 'rgba(10, 132, 255, 0.8)';
                    box.style.borderColor = 'yellow';
                }
            }
            toggle = !toggle;
        }, 300);

        if (wakeLock) wakeLock.release();
        GM_xmlhttpRequest({ method: "POST", url: URLS.ALARM });
        setInterval(() => { GM_xmlhttpRequest({ method: "POST", url: URLS.ALARM }); }, 5000);
    }

    function reportSuccessToDashboard() {
        GM_setValue("cfl_total_done", currentCount + 1);
        let refCode = "Unknown";
        try { if (window.location.href.includes("code=")) refCode = window.location.href.split("code=")[1].split("&")[0]; } catch(e) {}

        GM_xmlhttpRequest({
            method: "POST", url: URLS.LOG, headers: { "Content-Type": "application/x-www-form-urlencoded" }, data: "code=" + refCode
        });
    }

    async function requestWakeLock() {
        try { if ('wakeLock' in navigator) wakeLock = await navigator.wakeLock.request('screen'); } catch (err) {}
    }

    function injectPopupKiller() {
        const script = document.createElement('script');
        script.textContent = `
            (function() {
                window.alert = function(msg) {
                    msg = String(msg || "");
                    if (msg.includes("Invitation accepted") || msg.includes("already been invited")) {
                        localStorage.setItem('cfl_bot_status', 'SUCCESS: Invitation Accepted');
                        return true;
                    }
                    if (msg.includes("busy") || msg.includes("Network") || msg.includes("Confirm Passing")) return true;
                    return true;
                };
                window.confirm = window.alert;
            })();
        `;
        (document.head || document.documentElement).appendChild(script);
        script.remove();
    }
    injectPopupKiller();

    function wipeAndReload() {
        GM_setValue("cfl_loop_index", savedIndex + 1);
        localStorage.removeItem('cfl_final_timer_start');
        setTimeout(() => {
            updateStatus("🧹 WIPING Data...", "#ff9f0a");
            localStorage.clear();
            sessionStorage.clear();
            const cookies = document.cookie.split(";");
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i];
                const eqPos = cookie.indexOf("=");
                const name = eqPos > -1 ? cookie.substr(0, eqPos) : cookie;
                document.cookie = name + "=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/";
                document.cookie = name + "=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/;domain=" + window.location.hostname;
            }
            window.location.reload();
        }, 1000);
    }

    function humanClick(element) {
        if (!element) return;
        element.scrollIntoView({behavior: "smooth", block: "center"});
        element.click();
    }

    function typeValue(element, value) {
        if (!element) return;
        let nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
        nativeInputValueSetter.call(element, value);
        element.dispatchEvent(new Event('input', { bubbles: true }));
        element.dispatchEvent(new Event('change', { bubbles: true }));
    }

    requestWakeLock();

    setInterval(() => {
        // --- START/STOP CHECK ---
        if (!isRunning) return;

        if (limitValue > 0 && currentCount >= limitValue) {
            updateStatus("⛔ LIMIT REACHED. STOPPING.", "#ff453a");
            isRunning = false;
            GM_setValue("cfl_is_running", false);
            return;
        }

        if (alarmTriggered) return;
        if (!wakeLock) requestWakeLock();

        const timerStart = localStorage.getItem('cfl_final_timer_start');
        if (timerStart) {
            const elapsed = (Date.now() - parseInt(timerStart)) / 1000;
            if (elapsed < CONFIG.FINAL_TIMEOUT) {
                updateStatus(`⏳ Final Timer: ${Math.floor(elapsed)}s`, "#64d2ff");
            } else {
                updateStatus("⚠️ TIMEOUT! Resetting.", "#ff453a");
                wipeAndReload();
                return;
            }
        }

        const botStatus = localStorage.getItem('cfl_bot_status');
        if (botStatus) {
            updateStatus(`🏆 ${botStatus}`, "#64d2ff");
            if (botStatus.includes("Invitation Accepted") || botStatus.includes("already been invited")) {
                reportSuccessToDashboard();
            }
            localStorage.removeItem('cfl_bot_status');
            setTimeout(wipeAndReload, 1500);
            return;
        }

        const successText = xpath("//div[contains(text(), 'Draw(') or contains(text(), 'Log in to draw')]");
        if (successText) {
            updateStatus("🏆 LOGIN SUCCESS (No Invite)", "#64d2ff");
            setTimeout(wipeAndReload, 1500);
            return;
        }

        if (scriptStep === 4) {
            const skipBtn = qs('button[name="confirm"]') || xpath("//button[contains(., 'Skip')]");
            if (skipBtn) { humanClick(skipBtn); localStorage.setItem('cfl_final_timer_start', Date.now()); scriptStep = 5; return; }
        }

        if (scriptStep === 3) {
            const continueBtn = xpath("//button[contains(., 'Continue')]");
            if (continueBtn && !continueBtn.disabled) { humanClick(continueBtn); localStorage.setItem('cfl_final_timer_start', Date.now()); scriptStep = 4; return; }
        }

        if (scriptStep === 28) {
            updateStatus("⚡ Unlocking Continue...", "#ff9f0a");
            const codeInput = qs('input[placeholder="Verification code"]');
            const emailInput = qs("#registerForm_account");
            if (codeInput) { codeInput.focus(); codeInput.click(); }
            if (emailInput) { emailInput.focus(); emailInput.click(); }
            setTimeout(() => { scriptStep = 3; }, 800);
            return;
        }

        if (scriptStep === 2) {
            const checkbox = qs('.infinite-checkbox-input[type="checkbox"]');
            if (checkbox) { if (!checkbox.checked) checkbox.click(); scriptStep = 28; return; }
            else { const continueBtn = xpath("//button[contains(., 'Continue')]"); if(continueBtn) scriptStep = 3; }
        }

        if (scriptStep === 25) {
            const regionBox = qs('.infinite-select-selector');
            const regionText = qs('.infinite-select-selection-item');
            if (regionBox && regionText) {
                const currentRegion = regionText.innerText.trim() || regionText.title;
                if (currentRegion === "Philippines") { updateStatus("✅ Region Correct"); scriptStep = 2; return; }
                else {
                    if (regionTimer === 0) { updateStatus(`Opening Region...`, "#ff9f0a"); regionBox.click(); regionTimer = Date.now(); return; }
                    if (Date.now() - regionTimer < 1000) { updateStatus("⌛ Waiting for dropdown...", "#ffd60a"); return; }
                    const searchInput = qs('#area');
                    if (searchInput) {
                        updateStatus("⌨️ Typing Philippines...", "#0a84ff");
                        typeValue(searchInput, "Philippines");
                        setTimeout(() => {
                             searchInput.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, keyCode: 13, key: "Enter" }));
                             regionTimer = 0;
                        }, 500);
                    } else { regionTimer = 0; }
                }
            } else { scriptStep = 2; }
            return;
        }

        if (scriptStep === 1) {
            if (emailPollStartTime === 0) emailPollStartTime = Date.now();
            const waitTime = (Date.now() - emailPollStartTime) / 1000;

            if (waitTime > CONFIG.EMAIL_POLL_TIMEOUT) { triggerServerAlarm(); return; }

            if (!isPolling) {
                isPolling = true;
                updateStatus(`📡 Waiting for email (${Math.floor(waitTime)}s)...`);
                GM_xmlhttpRequest({
                    method: "GET", url: URLS.GET_CODE, onload: function(response) {
                        try {
                            const data = JSON.parse(response.responseText);
                            if (data.status === "found" && data.code) {
                                updateStatus("✅ CODE: " + data.code, "#64d2ff");
                                const codeInput = qs('input[placeholder="Verification code"]');
                                if (codeInput) { typeValue(codeInput, data.code); scriptStep = 25; emailPollStartTime = 0; }
                            }
                        } catch (e) { }
                        setTimeout(() => { isPolling = false; }, 3000);
                    }, onerror: function() { setTimeout(() => { isPolling = false; }, 3000); }
                });
            }
        }

        if (scriptStep === 0) {
            const emailField = qs("#registerForm_account");
            const getCodeBtn = xpath("//button[contains(., 'Get code')]");
            if (emailField && getCodeBtn) {
                if (emailField.value === EMAIL_TO_USE && getCodeBtn.disabled) {
                    updateStatus("⚡ Enabling Button...", "#ff9f0a"); typeValue(emailField, EMAIL_TO_USE); return;
                }
                if (emailField.value === EMAIL_TO_USE && !getCodeBtn.disabled) {
                    if (getCodeBtn.dataset.clicked) return;
                    getCodeBtn.dataset.clicked = "true";
                    updateStatus("⏳ Waiting 2s...", "#ffd60a");
                    setTimeout(() => {
                        updateStatus("🖱️ CLICKING", "#0a84ff");
                        getCodeBtn.click();
                        scriptStep = 1;
                        setTimeout(() => { if(scriptStep === 0) delete getCodeBtn.dataset.clicked; }, 5000);
                    }, 2000);
                }
            }
        }

        const emailInput = qs("#registerForm_account");
        if (scriptStep === 0 && emailInput && emailInput.value === "") typeValue(emailInput, EMAIL_TO_USE);

        const registerBtn = xpath("//span[contains(text(), 'Register for free')]");
        if (registerBtn && !qs("#registerForm_account")) humanClick(registerBtn);

        const loginBtn = qs("#pop2LoginBtn");
        if (loginBtn && !registerBtn && !emailInput) humanClick(loginBtn);

    }, 1000);

})();
