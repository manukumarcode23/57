# Telegram File Sharing Bot

## Overview
This Python-based Telegram bot offers a scalable file-sharing solution, allowing users to upload various file types (videos, zip, apk, documents) to Telegram and generate downloadable/streaming web links. It is designed to be a user-friendly platform for content creators, facilitating efficient media sharing, content management, statistics tracking, and mobile application integration. The project has potential for monetization through an ad-supported model.

## Recent Changes (December 3, 2025)
- **Quick-Add API Keys in Admin Panel**: Enhanced Admin API Keys page with one-click buttons to add pre-configured payment API endpoints:
  - Payment API: For all /api/payment/* endpoints (create-qr, check-status, plans, subscription-status, expire)
  - Ads API: For advertisement-related endpoints
  - Subscription API: For subscription management endpoints
  - Payment Webhook: For payment gateway callback notifications
  - Auto-generates secure API keys when clicked
  - Updated api_auth.py with proper endpoint mappings for all new endpoints

- **Centralized API Token Management**: Added a dedicated section in admin settings to configure authentication tokens for all APIs in one place:
  - Global API Token (master key): Works for all APIs if specific tokens are not set
  - Ads API Token: Specific token for /api/banner_ads, /api/interstitial_ads, /api/rewarded_ads, /api/all_ads
  - Payment API Token: Specific token for /api/payment/* endpoints
  - Token visibility toggle and auto-generation buttons in the UI
  - Priority-based authentication: Specific token > Global token > ApiEndpointKey > Environment variable fallback
  - Environment variable support: AD_API_TOKEN, PAYMENT_API_TOKEN, GLOBAL_API_TOKEN

## Previous Changes (November 17, 2025)
- **Enhanced Crop Button with Visual Feedback**: Improved the "Crop & Upload" button in thumbnail cropping modal:
  - Added loading spinner and "Processing..." text while cropping
  - Button disables during processing to prevent duplicate clicks
  - Comprehensive error handling with user-friendly error messages
  - Console logging for debugging any crop failures
  - Clear success message: "✓ Image cropped successfully! Now click 'Upload Thumbnail' to save."
  - Modal automatically closes after successful crop
  
- **Thumbnail Aspect Ratio Validation and Cropping**: Implemented strict thumbnail requirements with user-friendly cropping:
  - Required dimensions: 1280 x 720 pixels (16:9 YouTube standard aspect ratio)
  - Format: JPEG only (all images automatically converted to JPEG)
  - Interactive image cropping: Publishers can upload any image format (JPG, PNG, WebP) and crop to 16:9 ratio using Cropper.js
  - Automatic validation: Backend validates aspect ratio and auto-resizes images with correct ratio
  - Smart conversion: All uploaded images are converted to RGB JPEG format regardless of input
  - Clear requirements display: UI shows detailed thumbnail specifications before upload
  - Crop modal: Non-16:9 images automatically trigger an interactive crop tool with 16:9 constraint
  
- **Enhanced Thumbnail Upload with Status Tracking**: Improved publisher thumbnail upload experience with real-time status indicators:
  - Real upload progress tracking using XMLHttpRequest with actual network transfer percentage
  - Visual status badges on thumbnails: "Uploading" (blue, animated spinner), "Pending" (yellow, pulsing), "Approved" (green)
  - Animated progress bar showing upload completion percentage during file transfer
  - Upload button changes to "Uploading..." state with spinner animation during upload
  - Proper error handling that restores previous badge state if upload fails
  - Clear success messages indicating pending admin approval after upload
  - Rejected thumbnails are deleted and revert to "No thumbnail uploaded" placeholder

- **Workflow Cleanup**: Removed duplicate Web Server workflow to fix port conflict - the Telegram Bot workflow now properly runs both the bot and web server on port 5000

## Previous Changes (November 13, 2025)
- **Interactive Dashboard Buttons**: Transformed all stats cards into clickable interactive buttons with modern UI enhancements.
- **Fixed Graph Rendering Issues**: Updated Chart.js initialization in both publisher dashboard and statistics pages to properly wait for the library to load and handle errors gracefully. All charts now render correctly on both desktop and mobile devices.
- **Content Security Policy Update**: Added cdn.jsdelivr.net to allowed script sources to enable Chart.js loading.
- **Database Initialization**: Fixed database setup to handle existing tables gracefully, preventing duplicate table errors on restart.
- **Workflow Configuration**: Removed duplicate web server workflow since the Telegram Bot workflow already includes the web server on port 5000.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture

### Core Design
The bot uses a modular architecture with a Telegram Bot Layer (Telethon with plugins) and a Web Server Layer (Quart, Uvicorn) for file access and streaming. Data persistence is handled by PostgreSQL with SQLAlchemy. Security features include token-based access, Android ID validation, user whitelisting, and multi-layered content scanning. Files are automatically forwarded to a Telegram channel, and unique hash IDs are generated for link management.

### Key Features
- **Plugin System**: Dynamic loading of plugins for various functionalities.
- **UI/UX**: Consistent cyan/turquoise color scheme, Jinja2 templates, Video.js player, and an interactive dashboard with Chart.js.
- **Real-Time Upload Progress**: File upload page displays live progress with percentage, upload speed (MB/s), and transferred/total size using XMLHttpRequest.
- **Enhanced Performance Charts**: Dashboard charts display data with user-friendly date labels ("Nov 13" format), auto-skip functionality to prevent label overcrowding, and clear axis titles.
- **Bot Management**: Admin tools for managing helper bots.
- **HTTP Play Link System**: Generates `{BASE_URL}/play/{access_code}` links for app launches via Android intents.
- **Support Ticket System**: Publishers can create and manage support tickets.
- **Publisher Activity Tracking**: Logs publisher registrations, logins, IP geolocation, and device fingerprinting.
- **Referral & Earn System**: Configurable milestone-based rewards and automatic referral code generation.
- **Thumbnail System**: Professional thumbnail generation with custom branding.
- **Maintenance Mode**: Admin-controlled system wide maintenance.
- **Video Description Management**: Publishers can set default or custom video descriptions.
- **Subscription Payment System**: Integrated Paytm gateway with QR codes, UPI links, and automated verification.
- **Payment API System**: RESTful API for subscription payments with multiple authentication methods and automatic subscription activation.
- **Admin Payment Management**: Comprehensive admin panel for payment tracking and manual premium access granting with audit logging.
- **Premium User Publisher Earnings**: Publishers earn when premium users generate links to their videos, with configurable rates and monthly limits.

### System Design Choices
- **Unlimited Device-Specific Link Generation**: Multiple links can be generated per hash ID for different `android_id`s.
- **Auto-Delete Old Links**: Existing links are deleted when new ones are generated for the same `android_id` and `hash_id`.
- **Flexible Callback System**: `/api/postback` supports both GET and POST requests.
- **Mobile App Integration**: `/play/<hash_id>` landing pages for Android deep-linking.
- **API Parameter Standardization**: `android_id` used consistently across API endpoints.
- **Enhanced Ads API**: Supports per-device daily limits and prioritized ad networks.
- **Automatic Telegram Account Management**: Features unlinking and API key validation.
- **File Type Identification**: Download links and API responses include `file_type`.
- **User-Friendly File References**: Replaces technical hash IDs with clickable HTTP play links.
- **Admin Features**: Customizable impression rates, cutback percentages, and minimum withdrawal amounts.
- **Deployment**: Designed for Virtual Machine (VM) deployment for persistent bot connections.

## External Dependencies

### Core Libraries
- **Telethon**: Telegram client library.
- **Quart**: Async web framework.
- **Uvicorn**: ASGI server.
- **cryptg**: Cryptographic library.
- **SQLAlchemy**: ORM for database interaction.
- **Pillow**: For image manipulation.

### Frontend Dependencies
- **Video.js**: HTML5 video player.
- **Chart.js**: For interactive data visualization.
- **Font Awesome**: Icon library.
- **device-fingerprint.js**: Client-side device fingerprinting.

### Required Environment Variables
- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `TELEGRAM_CHANNEL_ID`, `OWNER_ID`, `BASE_URL`, `DATABASE_URL`.
- `PAYTM_MID`, `PAYTM_UPI_ID`, `PAYTM_UNIT_ID`, `PAYTM_SIGNATURE` (for payment system).

### System Dependencies
- **ffmpeg**: For video metadata extraction.

### External Services
- **Telegram Bot API**: For bot functionality.
- **Telegram MTProto API**: For direct file operations.
- **ip-api.com**: Geolocation API.
- **CDN Services**: For serving frontend assets.