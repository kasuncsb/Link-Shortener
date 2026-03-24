// API Configuration
// Load runtime config from /config.json
let API_BASE = '';
let MIN_CUSTOM_CODE_LENGTH = 5;
let MAX_CUSTOM_CODE_LENGTH = 20;

async function loadRuntimeConfig() {
    try {
        const res = await fetch('/config.json', {cache: 'no-store'});
        if (!res.ok) throw new Error('no config');
        const cfg = await res.json();
        if (typeof cfg.API_BASE === 'string' && cfg.API_BASE.trim()) {
            API_BASE = cfg.API_BASE;
        } else if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
            API_BASE = 'http://127.0.0.1:17321';
        }
        if (Number.isInteger(cfg.MIN_CUSTOM_CODE_LENGTH) && cfg.MIN_CUSTOM_CODE_LENGTH > 0) {
            MIN_CUSTOM_CODE_LENGTH = cfg.MIN_CUSTOM_CODE_LENGTH;
        }
        if (Number.isInteger(cfg.MAX_CUSTOM_CODE_LENGTH) && cfg.MAX_CUSTOM_CODE_LENGTH >= MIN_CUSTOM_CODE_LENGTH) {
            MAX_CUSTOM_CODE_LENGTH = cfg.MAX_CUSTOM_CODE_LENGTH;
        }
    } catch (e) {
        // fallback: if hostname indicates local, default to localhost API
        if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
            API_BASE = 'http://127.0.0.1:17321';
        }
    }
}

// DOM Elements
const elements = {
    form: document.getElementById('shorten-form'),
    urlInput: document.getElementById('url-input'),
    shortenBtn: document.getElementById('shorten-btn'),
    btnText: document.querySelector('.btn-text'),
    btnLoader: document.querySelector('.btn-loader'),
    advancedToggle: document.getElementById('advanced-toggle'),
    advancedOptions: document.getElementById('advanced-options'),
    customSuffix: document.getElementById('custom-suffix'),
    suffixStatus: document.getElementById('suffix-status'),
    expiryPills: document.getElementById('expiry-pills'),
    expiryDate: document.getElementById('expiry-date'),
    errorMessage: document.getElementById('error-message'),
    successModal: document.getElementById('success-modal'),
    modalClose: document.getElementById('modal-close'),
    resultLink: document.getElementById('result-link'),
    copyBtn: document.getElementById('copy-btn'),
    copyIcon: document.getElementById('copy-icon'),
    checkIcon: document.getElementById('check-icon'),
    qrCode: document.getElementById('qr-code'),
    expiresInfo: document.getElementById('expires-info'),
    createAnother: document.getElementById('create-another'),
    successAnimation: document.getElementById('success-animation')
};

// State
let suffixCheckTimeout = null;
let isSubmitting = false;
const DEFAULT_CODE_LENGTH = 7;
let lastSubmittedExpiryDays = null;

function parseExpiryDate(value) {
    if (!value) return null;
    let v = String(value).trim();
    if (!v) return null;
    if (v.includes(' ') && !v.includes('T')) {
        v = v.replace(' ', 'T');
    }
    const hasTz = /([zZ]|[+-]\d{2}:?\d{2})$/.test(v);
    return new Date(hasTz ? v : v + 'Z');
}

function getTypicalShortUrlLength() {
    const base = (window.location.origin || '').replace(/\/+$/, '');
    return `${base}/${'x'.repeat(DEFAULT_CODE_LENGTH)}`.length;
}

function applyCustomCodeLimitsToInput() {
    if (!elements.customSuffix) return;
    elements.customSuffix.minLength = MIN_CUSTOM_CODE_LENGTH;
    elements.customSuffix.maxLength = MAX_CUSTOM_CODE_LENGTH;
}

// Initialize
// Initialize after runtime config is loaded so API_BASE is correct
loadRuntimeConfig().then(() => {
    const init = () => {
        try {
            applyCustomCodeLimitsToInput();
            setupEventListeners();
            checkForRedirectError();
        } catch (e) {
            // if elements not present, fail gracefully
            console.error('Initialization error', e);
        }
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
});

function setupEventListeners() {
    // Form submission
    elements.form.addEventListener('submit', handleSubmit);
    
    // Advanced toggle
    elements.advancedToggle.addEventListener('click', toggleAdvancedOptions);
    
    // Custom suffix validation
    elements.customSuffix.addEventListener('input', handleSuffixInput);
    
    // Modal close
    elements.modalClose.addEventListener('click', closeSuccessModal);
    elements.successModal.querySelector('.modal-backdrop').addEventListener('click', closeSuccessModal);
    
    // Copy button
    elements.copyBtn.addEventListener('click', copyToClipboard);
    
    // Create another
    elements.createAnother.addEventListener('click', createAnotherLink);

    // Expiry pills
    setupExpiryPills();
    
    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeSuccessModal();
        }
    });

    // CSP-safe context-menu blocking for specific visual elements.
    document.querySelectorAll('[data-no-contextmenu="true"]').forEach((node) => {
        node.addEventListener('contextmenu', (ev) => ev.preventDefault());
    });
}

// Render a styled QR code using qr-code-styling when available, otherwise fall back to API image
let currentStyledQr = null;
function renderStyledQRCode(data) {
    // Clear previous
    elements.qrCode.innerHTML = '';

    // Fixed style: modules = dots, finder = rounded squares
    const dotsType = 'dots';

    if (window.QRCodeStyling) {
        try {
            currentStyledQr = new QRCodeStyling({
                width: 140,
                height: 140,
                type: 'svg',
                data,
                dotsOptions: {
                    color: '#000000',
                    type: dotsType
                },
                cornersSquareOptions: {
                    color: '#000000',
                    type: 'rounded'
                },
                cornersDotOptions: {
                    color: '#000000',
                    type: 'rounded'
                },
                backgroundOptions: {
                    color: '#ffffff'
                },
                imageOptions: {
                    crossOrigin: 'anonymous',
                    margin: 0
                }
            });

            // Append to container
            currentStyledQr.append(elements.qrCode);
            return;
        } catch (e) {
            // fallthrough to image fallback
            console.warn('Styled QR render failed, falling back to static image', e);
        }
    }

    // Fallback: use external API image
    try {
        const img = document.createElement('img');
        img.alt = 'QR code';
        img.width = 140;
        img.height = 140;
        img.className = 'qr-img';
        img.src = `https://api.qrserver.com/v1/create-qr-code/?size=140x140&data=${encodeURIComponent(data)}`;
        elements.qrCode.appendChild(img);
    } catch (e) {
        const p = document.createElement('p');
        p.textContent = data;
        p.className = 'qr-fallback';
        elements.qrCode.appendChild(p);
    }
}

function setupExpiryPills() {
    if (!elements.expiryPills) return;
    const radios = elements.expiryPills.querySelectorAll('input[type="radio"]');

    // Set min/max on the date picker
    const today = new Date();
    const maxDate = new Date();
    maxDate.setFullYear(maxDate.getFullYear() + 1);
    elements.expiryDate.min = today.toISOString().split('T')[0];
    elements.expiryDate.max = maxDate.toISOString().split('T')[0];

    // Force deterministic default so browser restore/autofill can't keep old values.
    const noneRadio = elements.expiryPills.querySelector('input[value="none"]');
    if (noneRadio) {
        noneRadio.checked = true;
    }
    elements.expiryDate.classList.add('hidden');
    elements.expiryDate.value = '';

    radios.forEach(radio => {
        radio.addEventListener('change', () => {
            if (radio.value === 'custom') {
                elements.expiryDate.classList.remove('hidden');
                elements.expiryDate.focus();
            } else {
                elements.expiryDate.classList.add('hidden');
                elements.expiryDate.value = '';
            }
        });
    });
}

/**
 * Read the currently selected expiry as `expires_in_days` (int) or null for no expiry.
 */
function getSelectedExpiryDays() {
    if (!elements.expiryPills) return null;
    const checked = elements.expiryPills.querySelector('input[type="radio"]:checked');
    if (!checked) return null;
    const expiry = checked.value;
    if (expiry === 'none') return null;
    if (expiry === 'custom') {
        if (!elements.expiryDate.value) return null;
        // Compute diff using UTC midnight-to-midnight to avoid timezone edge cases
        const todayUTC = new Date(Date.UTC(new Date().getUTCFullYear(), new Date().getUTCMonth(), new Date().getUTCDate()));
        const parts = elements.expiryDate.value.split('-');
        const selectedUTC = new Date(Date.UTC(+parts[0], +parts[1] - 1, +parts[2]));
        const diffDays = Math.round((selectedUTC - todayUTC) / (1000 * 60 * 60 * 24));
        return diffDays >= 0 ? Math.min(diffDays, 365) : null;
    }
    return parseInt(expiry, 10);
}



function checkForRedirectError() {
    const urlParams = new URLSearchParams(window.location.search);
    const err = urlParams.get('error');
    if (err === 'notfound') {
        window.location.href = '/404.html';
    } else if (err === 'expired') {
        window.location.href = '/expired.html';
    }
} 

// Toggle Advanced Options
function toggleAdvancedOptions() {
    elements.advancedToggle.classList.toggle('active');
    elements.advancedOptions.classList.toggle('open');
}

// Suffix status helper — animates in/out smoothly
let _suffixClearTimer = null;
function setSuffixStatus(text, state = '') {
    if (_suffixClearTimer) { clearTimeout(_suffixClearTimer); _suffixClearTimer = null; }
    const el = elements.suffixStatus;
    if (text) {
        el.textContent = text;
        el.className = 'suffix-status' + (state ? ' ' + state : '') + ' visible';
    } else {
        el.className = 'suffix-status' + (state ? ' ' + state : '');  // remove visible → triggers collapse
        _suffixClearTimer = setTimeout(() => { el.textContent = ''; }, 260);
    }
}

// Suffix Validation
function handleSuffixInput(e) {
    const value = e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '');
    e.target.value = value;
    
    if (suffixCheckTimeout) clearTimeout(suffixCheckTimeout);
    
    if (!value) {
        setSuffixStatus('', '');
        return;
    }
    
    if (value.length < MIN_CUSTOM_CODE_LENGTH) {
        setSuffixStatus(`Use at least ${MIN_CUSTOM_CODE_LENGTH} characters`, 'taken');
        return;
    }

    if (value.length > MAX_CUSTOM_CODE_LENGTH) {
        setSuffixStatus(`Use at most ${MAX_CUSTOM_CODE_LENGTH} characters`, 'taken');
        return;
    }
    
    setSuffixStatus('Checking...', 'checking');
    
    suffixCheckTimeout = setTimeout(() => checkSuffixAvailability(value), 400);
}

async function checkSuffixAvailability(suffix) {
    try {
        const response = await fetch(`${API_BASE}/api/check/${suffix}`);
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(extractErrorMessage(data, response.status) || 'Could not verify right now');
        }
        
        if (data.available) {
            setSuffixStatus('✓ Available', 'available');
        } else {
            if (data.reason === 'reserved') {
                setSuffixStatus('✗ Reserved word', 'taken');
            } else if (data.reason === 'taken') {
                setSuffixStatus('✗ Already taken', 'taken');
            } else {
                setSuffixStatus('✗ Not available', 'taken');
            }
        }
    } catch (error) {
        setSuffixStatus('Could not verify now', '');
    }
}

// Form Submission
async function handleSubmit(e) {
    e.preventDefault();
    
    if (isSubmitting) return;
    
    const url = elements.urlInput.value.trim();
    if (!url) return;
    
    // Validate URL
    if (!isValidUrl(url)) {
        showError('Please enter a valid link that starts with http:// or https://');
        return;
    }

    if (url.length <= getTypicalShortUrlLength()) {
        showError('That link is already very short. Please enter the original long link.');
        return;
    }
    
    // Check custom suffix
    const customSuffix = elements.customSuffix.value.trim();
    if (customSuffix && customSuffix.length < MIN_CUSTOM_CODE_LENGTH) {
        showError(`Your custom short link needs at least ${MIN_CUSTOM_CODE_LENGTH} characters.`);
        return;
    }
    if (customSuffix && customSuffix.length > MAX_CUSTOM_CODE_LENGTH) {
        showError(`Your custom short link can be at most ${MAX_CUSTOM_CODE_LENGTH} characters.`);
        return;
    }
    
    isSubmitting = true;
    setLoadingState(true);
    hideError();
    
    try {
        const payload = { url };

        if (customSuffix) {
            payload.custom_code = customSuffix;
        }

        const expiryDays = getSelectedExpiryDays();
        lastSubmittedExpiryDays = expiryDays;
        if (expiryDays !== null) {
            payload.expires_in_days = expiryDays;
        }
        
        const response = await fetch(`${API_BASE}/api/shorten`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            // Rate limit handling
            if (response.status === 429) {
                const retryAfter = response.headers.get('Retry-After');
                let msg = extractErrorMessage(data) || "You're making requests too quickly. Please wait and try again.";
                if (retryAfter) msg += ` Retry after ${retryAfter} seconds.`;
                throw new Error(msg);
            }

            throw new Error(extractErrorMessage(data, response.status) || 'We could not shorten your link right now. Please try again.');
        }

        showSuccessModal(data);
        
    } catch (error) {
        const message = (error && typeof error.message === 'string' && error.message.trim())
            ? error.message
            : 'Something went wrong. Please try again.';
        showError(message);
    } finally {
        isSubmitting = false;
        setLoadingState(false);
    }
}

/**
 * Safely extract a human-readable error message from a FastAPI response body.
 * detail can be a string (app-level error) or an array of objects (422 Pydantic validation).
 */
function extractErrorMessage(data, status = 0) {
    if (!data) return null;
    if (typeof data.error === 'string' && data.error.trim()) return data.error;
    if (typeof data.detail === 'string' && data.detail.trim()) return data.detail;
    if (Array.isArray(data.detail) && data.detail.length > 0) {
        const first = data.detail[0];
        if (first && typeof first.msg === 'string' && first.msg.trim()) return first.msg;
    }

    if (status === 400 || status === 422) return 'Please check your link and try again.';
    if (status === 404) return "We couldn't find that link.";
    if (status === 410) return 'This link is no longer available.';
    if (status === 429) return "You're making requests too quickly. Please wait and try again.";
    if (status >= 500) return 'Something went wrong on our side. Please try again in a moment.';
    return 'Something went wrong. Please try again.';
}

function isValidUrl(string) {
    try {
        const url = new URL(string);
        return url.protocol === 'http:' || url.protocol === 'https:';
    } catch {
        return false;
    }
}

function setLoadingState(loading) {
    elements.shortenBtn.disabled = loading;
    elements.btnText.classList.toggle('hidden', loading);
    elements.btnLoader.classList.toggle('hidden', !loading);
}

// Error Handling
let _errorHideTimer = null;
function showError(message) {
    if (_errorHideTimer) { clearTimeout(_errorHideTimer); _errorHideTimer = null; }
    elements.errorMessage.textContent = message;
    elements.errorMessage.classList.add('visible');
}

function hideError() {
    elements.errorMessage.classList.remove('visible');
    _errorHideTimer = setTimeout(() => { elements.errorMessage.textContent = ''; }, 300);
}

// Success Modal
function showSuccessModal(data) {
    const shortUrl = data.short_url;
    elements.resultLink.value = shortUrl;
    
    // Generate QR Code using styled renderer when available (fallback to image service)
    elements.qrCode.innerHTML = '';
    renderStyledQRCode(shortUrl);
    
    // Expiry info
    if (data.expires_at) {
        const expiryDate = parseExpiryDate(data.expires_at);
        if (!expiryDate || isNaN(expiryDate.getTime())) {
            elements.expiresInfo.textContent = `Expires at ${data.expires_at}`;
        } else {
            elements.expiresInfo.textContent = `Expires on ${expiryDate.toLocaleDateString('en-US', { 
                year: 'numeric', 
                month: 'long', 
                day: 'numeric' 
            })}`;
        }
    } else if (Number.isInteger(lastSubmittedExpiryDays) && lastSubmittedExpiryDays > 0) {
        // Fallback when API date is unavailable: compute exact date from submitted expiry.
        const approxExpiry = new Date();
        approxExpiry.setDate(approxExpiry.getDate() + lastSubmittedExpiryDays);
        elements.expiresInfo.textContent = `Expires on ${approxExpiry.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        })}`;
    } else {
        elements.expiresInfo.textContent = 'This link never expires';
    }
    
    elements.successModal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    
    // Play animation
    if (elements.successAnimation) {
        elements.successAnimation.stop();
        elements.successAnimation.play();
    }

}


function closeSuccessModal() {
    elements.successModal.classList.add('hidden');
    document.body.style.overflow = '';
    resetCopyButton();
}

function createAnotherLink() {
    closeSuccessModal();
    elements.form.reset();
    elements.customSuffix.value = '';
    elements.suffixStatus.textContent = '';
    elements.suffixStatus.className = 'suffix-status';
    elements.urlInput.focus();

    // Reset expiry to default (No Expiry)
    if (elements.expiryPills) {
        const noneRadio = elements.expiryPills.querySelector('input[value="none"]');
        if (noneRadio) noneRadio.checked = true;
    }
    elements.expiryDate.classList.add('hidden');
    elements.expiryDate.value = '';
    lastSubmittedExpiryDays = null;
    
    if (elements.advancedOptions.classList.contains('open')) {
        toggleAdvancedOptions();
    }
}

// Copy to Clipboard
async function copyToClipboard() {
    try {
        await navigator.clipboard.writeText(elements.resultLink.value);
        
        elements.copyBtn.classList.add('copied');
        elements.copyIcon.classList.add('hidden');
        elements.checkIcon.classList.remove('hidden');
        
        setTimeout(resetCopyButton, 2000);
    } catch (error) {
        // Fallback
        elements.resultLink.select();
        document.execCommand('copy');
    }
}

function resetCopyButton() {
    elements.copyBtn.classList.remove('copied');
    elements.copyIcon.classList.remove('hidden');
    elements.checkIcon.classList.add('hidden');
}
