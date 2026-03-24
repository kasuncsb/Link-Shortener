const express = require('express');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;
const API_BASE = process.env.API_BASE || 'http://127.0.0.1:17321';
const MIN_CUSTOM_CODE_LENGTH = Number.parseInt(process.env.MIN_CUSTOM_CODE_LENGTH || '5', 10);
const MAX_CUSTOM_CODE_LENGTH = Number.parseInt(process.env.MAX_CUSTOM_CODE_LENGTH || '20', 10);

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
