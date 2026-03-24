const express = require('express');
const path = require('path');
const http = require('http');
const https = require('https');

const app = express();
const PORT = process.env.PORT || 17320;
// Default to same-origin API path via reverse proxy in production.
// For local development, set API_BASE explicitly if needed.
const API_BASE = process.env.API_BASE || '';
const INTERNAL_API_BASE = process.env.INTERNAL_API_BASE || 'http://127.0.0.1:17321';
const MIN_CUSTOM_CODE_LENGTH = Number.parseInt(process.env.MIN_CUSTOM_CODE_LENGTH || '5', 10);
const MAX_CUSTOM_CODE_LENGTH = Number.parseInt(process.env.MAX_CUSTOM_CODE_LENGTH || '20', 10);

// Only forward safe headers to backend (avoid leaking cookies/auth tokens).
const SAFE_PROXY_HEADERS = ['content-type', 'accept', 'user-agent', 'accept-language', 'content-length'];

function proxyApiRequest(req, res) {
    const targetUrl = new URL(req.originalUrl, INTERNAL_API_BASE);
    const transport = targetUrl.protocol === 'https:' ? https : http;

    const forwardHeaders = { host: targetUrl.host };
    for (const name of SAFE_PROXY_HEADERS) {
        if (req.headers[name]) forwardHeaders[name] = req.headers[name];
    }
    // Forward real client IP for rate limiting
    forwardHeaders['x-forwarded-for'] = req.headers['x-forwarded-for'] || req.socket.remoteAddress;
    forwardHeaders['x-real-ip'] = req.headers['x-real-ip'] || req.socket.remoteAddress;

    const proxyReq = transport.request(
        {
            protocol: targetUrl.protocol,
            hostname: targetUrl.hostname,
            port: targetUrl.port || (targetUrl.protocol === 'https:' ? 443 : 80),
            method: req.method,
            path: `${targetUrl.pathname}${targetUrl.search}`,
            headers: forwardHeaders
        },
        (proxyRes) => {
            res.status(proxyRes.statusCode || 502);
            Object.entries(proxyRes.headers).forEach(([key, value]) => {
                if (value !== undefined) {
                    res.setHeader(key, value);
                }
            });
            proxyRes.pipe(res);
        }
    );

    proxyReq.on('error', () => {
        if (!res.headersSent) {
            res.status(503).json({ error: 'API temporarily unavailable. Please try again.' });
            return;
        }
        res.end();
    });

    req.pipe(proxyReq);
}

// Limit request body size (1 MB) to prevent memory exhaustion.
app.use(express.json({ limit: '1mb' }));
app.use(express.urlencoded({ extended: false, limit: '1mb' }));

// Proxy all API calls to backend service inside the container.
app.use('/api', proxyApiRequest);

// Serve static files
app.use(express.static(path.join(__dirname, 'public')));

// Home route
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Runtime config for browser app
app.get('/config.json', (req, res) => {
    res.setHeader('Cache-Control', 'no-store');
    res.json({
        API_BASE,
        MIN_CUSTOM_CODE_LENGTH: Number.isFinite(MIN_CUSTOM_CODE_LENGTH) ? MIN_CUSTOM_CODE_LENGTH : 5,
        MAX_CUSTOM_CODE_LENGTH: Number.isFinite(MAX_CUSTOM_CODE_LENGTH) ? MAX_CUSTOM_CODE_LENGTH : 20
    });
});

// 404 page for all other routes
app.use((req, res) => {
    res.status(404).sendFile(path.join(__dirname, 'public', '404.html'));
});

app.listen(PORT, () => {
    console.log(`Frontend server running on http://localhost:${PORT}`);
});
