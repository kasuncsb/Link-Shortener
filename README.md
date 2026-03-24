# Link Shortener

<p align="left">
  <img src="frontend/public/images/logo.png" alt="Link Shortener" width="160" />
</p>

A clean, fast link shortener built for everyday sharing.

## Product highlights

- Shorten long URLs into easy-to-share links
- Choose your own custom suffix when available
- Set expiry windows or keep links permanent
- Preview destination metadata before sharing
- Show user-friendly pages for missing and expired links
- Keep creation flow simple and mobile-friendly

## Core features

### Link creation

- Paste a URL and generate a short link in one step
- Optional advanced controls for custom code and expiry
- Instant result popup with copy action and QR support

### Link behavior

- Fast redirects for active links
- Clear expired-link handling
- Consistent not-found behavior for unknown codes

### Sharing and previews

- Open Graph/Twitter-friendly metadata support
- Better-looking shares in messaging/social apps
- Branded fallback preview when destination metadata is limited

### Reliability and safety

- Basic per-IP rate limiting on creation endpoints
- Reserved route/code protection
- Health endpoints for service status checks

## API at a glance

- `POST /api/shorten` — create short link
- `GET /api/check/{code}` — check custom code availability
- `GET /api/preview/{code}` — preview destination URL
- `GET /{code}` — redirect short URL

## License

MIT © KasunCSB
