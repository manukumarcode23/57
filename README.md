# Video Streaming & Download Platform

A Telegram bot-based file sharing application with integrated video streaming, download capabilities, and ad monetization.

## 🎯 For Mobile App Developers

If you're building a mobile app that integrates with this API, start here:

### 📚 Mobile App Documentation

1. **[APP_FLOW_SIMPLE.md](./APP_FLOW_SIMPLE.md)** ⭐ **START HERE - EASIEST GUIDE**
   - Simple step-by-step flows
   - No code, just clear process
   - Intent flow + Network link flow
   - Perfect for AI to build app

2. **[API_README.md](./API_README.md)**
   - Quick start guide
   - Overview of features
   - Getting started steps

3. **[API_DOCUMENTATION.md](./API_DOCUMENTATION.md)**
   - Complete API reference
   - All endpoints with examples
   - Authentication & security

4. **[MOBILE_INTEGRATION_GUIDE.md](./MOBILE_INTEGRATION_GUIDE.md)**
   - Detailed integration guide
   - Process explanations
   - Deep link/Intent setup
   - UI/UX recommendations

5. **[API_FLOW.md](./API_FLOW.md)**
   - Visual flow diagrams
   - Complete user journey
   - Sequence diagrams

6. **[SUPPORTED_VIDEO_FORMATS.md](./SUPPORTED_VIDEO_FORMATS.md)** 🎬 **NEW!**
   - All supported video formats
   - Player features and capabilities
   - Browser compatibility guide
   - Best practices for video integration

### 🚀 Quick Start for Developers

```bash
# 1. Get your API token
Visit: https://your-domain.com/publisher

# 2. Read the documentation
Start with: API_README.md

# 3. Implement the flow
Follow: MOBILE_INTEGRATION_GUIDE.md
```

---

## 🏗️ System Overview

### For Administrators

This platform provides:
- **File Sharing** via Telegram bot
- **Web Interface** for uploads and playback
- **Publisher System** with analytics dashboard
- **Ad Management** with multiple networks
- **API System** for mobile app integration

### Core Features

- ✅ Video streaming with range request support
- ✅ **Multi-format support** (MP4, WebM, MOV, HLS streaming, and more)
- ✅ **Mobile-optimized player** for Android apps
- ✅ Secure download links with expiration
- ✅ Ad monetization (Rewarded, Interstitial, Banner)
- ✅ Publisher dashboard with analytics
- ✅ Admin panel for configuration
- ✅ Deep link support for Android apps
- ✅ RESTful API for mobile integration

---

## 📱 Mobile App Features

When integrated with a mobile app, users get:

1. **My Video** - Play device local videos
2. **Network Link** - Stream/download videos from URLs
3. **Downloaded Videos** - Offline playback

### User Flow
```
Enter video URL → Extract hash ID → Show rewarded ad → 
Show interstitial ads → Generate secure links → Stream/Download
```

---

## 🔧 Technical Stack

- **Backend:** Python (Quart framework)
- **Bot:** Telethon (Telegram API)
- **Database:** PostgreSQL
- **Web Server:** Uvicorn (ASGI)
- **Authentication:** Token-based API auth
- **Video Delivery:** Range request streaming

---

## 🌐 Web Endpoints

### User Facing
- `/` - Home page
- `/play/{hash_id}` - Video player with deep link
- `/stream/{file_id}` - Desktop video player (HTML5 formats)
- `/stream/mobile/{file_id}` - Mobile-optimized player  
- `/dl/{file_id}` - Direct download/streaming endpoint (accepts all formats)
- `/upload` - File upload interface

### Admin Panel
- `/admin/dashboard` - Admin dashboard
- `/admin/publishers` - Publisher management
- `/admin/ad-networks` - Ad network configuration
- `/admin/settings` - System settings

### Publisher Panel
- `/publisher/dashboard` - Publisher dashboard
- `/publisher/videos` - Video management
- `/publisher/api` - API key management

### API Endpoints
- `/api/request` - Request video access
- `/api/links` - Generate stream/download links
- `/api/rewarded_ads` - Get rewarded ad config
- `/api/interstitial_ads` - Get interstitial ad config
- `/api/banner_ads` - Get banner ad config
- `/api/tracking/postback` - Track impressions

---

## 📊 Analytics & Tracking

The platform tracks:
- Video upload statistics
- File access logs
- Ad impressions per publisher
- Revenue calculations
- Daily usage metrics

---

## 🔐 Security Features

- Token-based API authentication
- Temporary download/stream links (1 hour expiry)
- One-time use tokens
- File access logging
- Publisher authentication
- Admin role protection

---

## 💰 Monetization

### Ad Integration
- Multiple ad network support
- Daily limit configuration
- Priority-based network selection
- Automatic fallback mechanism
- Real-time impression tracking

### Revenue Sharing
- Publishers earn per impression
- Configurable impression rates
- Automated earnings calculation
- Dashboard analytics

---

## 🚀 Getting Started

### For Mobile Developers
1. Register as publisher at `/publisher/register`
2. Generate API token in dashboard
3. Read `API_README.md`
4. Follow `MOBILE_INTEGRATION_GUIDE.md`

### For Administrators
1. Access admin panel at `/admin`
2. Configure ad networks
3. Set impression rates
4. Manage publishers
5. Monitor analytics

### For Publishers
1. Register at `/publisher/register`
2. Upload videos via web or Telegram bot
3. Get API key for programmatic uploads
4. Track earnings in dashboard

---

## 📝 Project Structure

```
.
├── bot/
│   ├── plugins/          # Telegram bot commands & handlers
│   ├── server/           # Web server & API endpoints
│   ├── models.py         # Database models
│   └── config.py         # Configuration
├── API_README.md         # Mobile dev quick start
├── API_DOCUMENTATION.md  # Complete API reference
├── MOBILE_INTEGRATION_GUIDE.md  # Integration tutorial
├── API_FLOW.md          # Flow diagrams
└── README.md            # This file
```

---

## 🔄 Workflows

### Video Upload Flow
1. User sends file to Telegram bot
2. Bot uploads to Telegram channel
3. System generates hash ID
4. Returns shareable play link

### Mobile App Flow
1. User enters video URL
2. App extracts hash ID
3. Request video access (API)
4. Show rewarded ad
5. Show interstitial ads
6. Get stream/download links
7. Play or download video

### Deep Link Flow
1. User clicks play link in browser
2. Shows "Play in App" button
3. Opens mobile app via intent
4. App processes hash ID
5. Follows mobile app flow

---

## 📚 Additional Documentation

- `DEPLOYMENT_GUIDE.txt` - Server deployment instructions
- `VPS_SETUP.txt` - VPS configuration guide
- `replit.md` - Development notes & architecture

---

## 🛠️ Development

### Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment variables
DATABASE_URL=postgresql://...
BOT_TOKEN=your_telegram_bot_token
AD_API_TOKEN=your_api_token

# Run the application
python -m bot
```

### Environment Variables
- `DATABASE_URL` - PostgreSQL connection string
- `BOT_TOKEN` - Telegram bot token
- `AD_API_TOKEN` - API authentication token
- `API_ID` - Telegram API ID
- `API_HASH` - Telegram API hash
- `CHANNEL_ID` - Telegram channel ID for file storage

---

## 📞 Support

- **Mobile Developers:** Start with `API_README.md`
- **Publishers:** Access `/publisher/dashboard`
- **Administrators:** Access `/admin/dashboard`

---

## 📄 License

See terms of service at `/terms-of-service`  
Privacy policy at `/privacy-policy`

---

**Last Updated:** October 2025  
**Version:** 1.0
