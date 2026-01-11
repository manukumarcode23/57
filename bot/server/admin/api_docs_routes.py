from quart import Blueprint, render_template
from .utils import require_admin
from bot.config import Server

bp = Blueprint('admin_api_docs', __name__)

@bp.route('/api-documentation')
@require_admin
async def api_documentation():
    base_url = Server.BASE_URL
    
    api_endpoints = {
        'File Access & Link Generation': [
            {
                'method': 'POST',
                'endpoint': '/api/request',
                'description': 'Requests file access, linking the android_id to the file',
                'params': ['api_key', 'hash_id', 'android_id'],
                'example_link': None
            },
            {
                'method': 'GET/POST',
                'endpoint': '/api/postback',
                'description': 'Generates temporary stream and download links with callback support',
                'params': ['api_key', 'hash_id', 'android_id', 'callback_url (optional)', 'callback_method (optional)'],
                'example_link': f'{base_url}/api/postback?api_key=YOUR_API_KEY&hash_id=abc123def456789&android_id=sample_device_123'
            },
            {
                'method': 'POST',
                'endpoint': '/api/links',
                'description': 'Retrieves the generated stream and download links',
                'params': ['api_key', 'hash_id', 'android_id'],
                'example_link': None
            },
        ],
        'Tracking API': [
            {
                'method': 'GET',
                'endpoint': '/api/tracking/postback',
                'description': 'Tracks video impressions for publisher analytics',
                'params': ['api_key', 'hash_id', 'android_id', 'impression_date', 'country', 'region'],
                'example_link': f'{base_url}/api/tracking/postback?api_key=YOUR_API_KEY&hash_id=abc123def456789&android_id=sample_device_123&impression_date=2025-10-30&country=US&region=California'
            },
        ],
        'Advertisement APIs': [
            {
                'method': 'GET',
                'endpoint': '/api/banner_ads',
                'description': 'Retrieves banner ad networks sorted by priority',
                'params': ['token', 'android_id (optional)'],
                'example_link': f'{base_url}/api/banner_ads?token=YOUR_TOKEN&android_id=sample_device_123'
            },
            {
                'method': 'GET',
                'endpoint': '/api/interstitial_ads',
                'description': 'Retrieves interstitial ad networks sorted by priority',
                'params': ['token', 'android_id (optional)'],
                'example_link': f'{base_url}/api/interstitial_ads?token=YOUR_TOKEN&android_id=sample_device_123'
            },
            {
                'method': 'GET',
                'endpoint': '/api/rewarded_ads',
                'description': 'Retrieves rewarded ad networks sorted by priority',
                'params': ['token', 'android_id (optional)'],
                'example_link': f'{base_url}/api/rewarded_ads?token=YOUR_TOKEN&android_id=sample_device_123'
            },
            {
                'method': 'GET',
                'endpoint': '/api/all_ads',
                'description': 'Retrieves all active ad networks with their configurations',
                'params': ['token', 'android_id (optional)'],
                'example_link': f'{base_url}/api/all_ads?token=YOUR_TOKEN&android_id=sample_device_123'
            },
            {
                'method': 'POST',
                'endpoint': '/api/record_ad_play',
                'description': 'Records an ad play using a unique tracking token',
                'params': ['token', 'unique_id', 'android_id'],
                'example_link': None
            },
            {
                'method': 'GET',
                'endpoint': '/api/ad_limits',
                'description': 'Retrieves current ad limit counts for a specific device/IP',
                'params': ['token', 'android_id (optional)'],
                'example_link': f'{base_url}/api/ad_limits?token=YOUR_TOKEN&android_id=sample_device_123'
            },
        ],
        'Web Routes': [
            {
                'method': 'POST',
                'endpoint': '/upload',
                'description': 'Handles web-based file uploads',
                'params': ['file', 'csrf_token'],
                'example_link': None
            },
            {
                'method': 'GET',
                'endpoint': '/stream/<file_id>',
                'description': 'Streams video files with token authentication',
                'params': ['token (query param)'],
                'example_link': f'{base_url}/stream/12345?token=YOUR_TOKEN'
            },
            {
                'method': 'GET',
                'endpoint': '/dl/<file_id>',
                'description': 'Downloads files with token authentication and range request support',
                'params': ['token (query param)'],
                'example_link': f'{base_url}/dl/12345?token=YOUR_TOKEN'
            },
            {
                'method': 'GET',
                'endpoint': '/play/<hash_id>',
                'description': 'Landing page for video playback with deep linking support',
                'params': [],
                'example_link': f'{base_url}/play/abc123def456789'
            },
        ],
        'Authentication Routes': [
            {
                'method': 'POST',
                'endpoint': '/register',
                'description': 'Registers a new publisher account',
                'params': ['email', 'password', 'referral_code (optional)'],
                'example_link': None
            },
            {
                'method': 'POST',
                'endpoint': '/login',
                'description': 'Authenticates publisher login',
                'params': ['email', 'password'],
                'example_link': None
            },
            {
                'method': 'GET',
                'endpoint': '/logout',
                'description': 'Ends the publisher session',
                'params': [],
                'example_link': f'{base_url}/logout'
            },
        ],
        'Publisher Routes': [
            {
                'method': 'GET',
                'endpoint': '/publisher/dashboard',
                'description': 'Displays publisher dashboard',
                'params': [],
                'example_link': f'{base_url}/publisher/dashboard'
            },
            {
                'method': 'POST',
                'endpoint': '/publisher/generate-api-key',
                'description': 'Generates a new API key for the publisher',
                'params': ['csrf_token'],
                'example_link': None
            },
            {
                'method': 'POST',
                'endpoint': '/publisher/upload-video',
                'description': 'Uploads video via the publisher dashboard',
                'params': ['file', 'csrf_token'],
                'example_link': None
            },
            {
                'method': 'POST',
                'endpoint': '/publisher/delete-video/<file_id>',
                'description': "Deletes a publisher's video",
                'params': ['csrf_token'],
                'example_link': None
            },
            {
                'method': 'GET',
                'endpoint': '/publisher/videos',
                'description': "Displays publisher's video list and stats",
                'params': [],
                'example_link': f'{base_url}/publisher/videos'
            },
            {
                'method': 'GET',
                'endpoint': '/publisher/statistics',
                'description': 'Shows detailed statistics for selected videos',
                'params': [],
                'example_link': f'{base_url}/publisher/statistics'
            },
            {
                'method': 'GET',
                'endpoint': '/publisher/withdraw',
                'description': 'Manages withdrawal requests',
                'params': [],
                'example_link': f'{base_url}/publisher/withdraw'
            },
            {
                'method': 'POST',
                'endpoint': '/publisher/save-bank-account',
                'description': 'Saves publisher bank account details',
                'params': ['bank_name', 'account_number', 'account_holder', 'csrf_token'],
                'example_link': None
            },
            {
                'method': 'POST',
                'endpoint': '/publisher/request-withdrawal',
                'description': 'Requests a withdrawal',
                'params': ['amount', 'csrf_token'],
                'example_link': None
            },
            {
                'method': 'GET',
                'endpoint': '/publisher/tickets',
                'description': 'Manages publisher support tickets',
                'params': [],
                'example_link': f'{base_url}/publisher/tickets'
            },
            {
                'method': 'POST',
                'endpoint': '/publisher/tickets/create',
                'description': 'Creates a new support ticket',
                'params': ['subject', 'message', 'csrf_token'],
                'example_link': None
            },
            {
                'method': 'GET',
                'endpoint': '/publisher/tickets/<ticket_id>',
                'description': 'Views a specific ticket',
                'params': [],
                'example_link': f'{base_url}/publisher/tickets/123'
            },
            {
                'method': 'GET',
                'endpoint': '/publisher/api-management',
                'description': 'Manages API keys and linked bots',
                'params': [],
                'example_link': f'{base_url}/publisher/api-management'
            },
            {
                'method': 'GET',
                'endpoint': '/publisher/referrals',
                'description': 'Displays referral information and stats',
                'params': [],
                'example_link': f'{base_url}/publisher/referrals'
            },
        ],
        'Admin Routes': [
            {
                'method': 'GET',
                'endpoint': '/admin/dashboard',
                'description': 'Displays admin dashboard with system overview',
                'params': [],
                'example_link': f'{base_url}/admin/dashboard'
            },
            {
                'method': 'POST',
                'endpoint': '/admin/register-publisher',
                'description': 'Admin creates a new publisher account',
                'params': ['email', 'password', 'csrf_token'],
                'example_link': None
            },
            {
                'method': 'POST',
                'endpoint': '/admin/toggle-publisher/<publisher_id>',
                'description': 'Activates/deactivates publisher accounts',
                'params': ['csrf_token'],
                'example_link': None
            },
            {
                'method': 'GET',
                'endpoint': '/admin/publishers',
                'description': 'Lists all publishers',
                'params': [],
                'example_link': f'{base_url}/admin/publishers'
            },
            {
                'method': 'GET',
                'endpoint': '/admin/publisher/<publisher_id>/files',
                'description': "Views a publisher's files",
                'params': [],
                'example_link': f'{base_url}/admin/publisher/1/files'
            },
            {
                'method': 'POST',
                'endpoint': '/admin/delete-file/<file_id>',
                'description': 'Admin deletes a file',
                'params': ['csrf_token'],
                'example_link': None
            },
            {
                'method': 'GET',
                'endpoint': '/admin/ad-networks',
                'description': 'Manages ad network configurations',
                'params': [],
                'example_link': f'{base_url}/admin/ad-networks'
            },
            {
                'method': 'POST',
                'endpoint': '/admin/ad-networks/add',
                'description': 'Adds a new ad network',
                'params': ['network_name', 'banner_id', 'interstitial_id', 'rewarded_id', 'priority', 'csrf_token'],
                'example_link': None
            },
            {
                'method': 'POST',
                'endpoint': '/admin/ad-networks/edit/<network_id>',
                'description': 'Updates an existing ad network',
                'params': ['network_name', 'banner_id', 'interstitial_id', 'rewarded_id', 'priority', 'csrf_token'],
                'example_link': None
            },
            {
                'method': 'POST',
                'endpoint': '/admin/ad-networks/toggle/<network_id>',
                'description': 'Activates/deactivates an ad network',
                'params': ['csrf_token'],
                'example_link': None
            },
            {
                'method': 'POST',
                'endpoint': '/admin/ad-networks/delete/<network_id>',
                'description': 'Deletes an ad network',
                'params': ['csrf_token'],
                'example_link': None
            },
            {
                'method': 'GET',
                'endpoint': '/admin/settings',
                'description': 'Manages system settings',
                'params': [],
                'example_link': f'{base_url}/admin/settings'
            },
            {
                'method': 'POST',
                'endpoint': '/admin/settings/update',
                'description': 'Updates system settings',
                'params': ['impression_rate', 'minimum_withdrawal', 'ads_api_token', 'csrf_token', 'etc...'],
                'example_link': None
            },
            {
                'method': 'GET',
                'endpoint': '/admin/withdrawals',
                'description': 'Lists withdrawal requests',
                'params': [],
                'example_link': f'{base_url}/admin/withdrawals'
            },
            {
                'method': 'POST',
                'endpoint': '/admin/withdrawal/approve/<withdrawal_id>',
                'description': 'Approves a withdrawal request',
                'params': ['csrf_token'],
                'example_link': None
            },
            {
                'method': 'POST',
                'endpoint': '/admin/withdrawal/reject/<withdrawal_id>',
                'description': 'Rejects a withdrawal request',
                'params': ['csrf_token'],
                'example_link': None
            },
            {
                'method': 'GET',
                'endpoint': '/admin/bots',
                'description': 'Manages helper bots',
                'params': [],
                'example_link': f'{base_url}/admin/bots'
            },
            {
                'method': 'POST',
                'endpoint': '/admin/bots/add',
                'description': 'Adds a new helper bot',
                'params': ['bot_username', 'csrf_token'],
                'example_link': None
            },
            {
                'method': 'POST',
                'endpoint': '/admin/bots/edit/<bot_id>',
                'description': 'Updates a helper bot',
                'params': ['bot_username', 'csrf_token'],
                'example_link': None
            },
            {
                'method': 'POST',
                'endpoint': '/admin/bots/toggle/<bot_id>',
                'description': 'Activates/deactivates a helper bot',
                'params': ['csrf_token'],
                'example_link': None
            },
            {
                'method': 'POST',
                'endpoint': '/admin/bots/delete/<bot_id>',
                'description': 'Deletes a helper bot',
                'params': ['csrf_token'],
                'example_link': None
            },
            {
                'method': 'GET',
                'endpoint': '/admin/country-rates',
                'description': 'Manages country-specific impression rates',
                'params': [],
                'example_link': f'{base_url}/admin/country-rates'
            },
            {
                'method': 'POST',
                'endpoint': '/admin/country-rates/add',
                'description': 'Adds a new country rate',
                'params': ['country_code', 'rate', 'csrf_token'],
                'example_link': None
            },
            {
                'method': 'POST',
                'endpoint': '/admin/country-rates/update/<rate_id>',
                'description': 'Updates a country rate',
                'params': ['rate', 'csrf_token'],
                'example_link': None
            },
            {
                'method': 'POST',
                'endpoint': '/admin/country-rates/toggle/<rate_id>',
                'description': 'Activates/deactivates a country rate',
                'params': ['csrf_token'],
                'example_link': None
            },
            {
                'method': 'POST',
                'endpoint': '/admin/country-rates/delete/<rate_id>',
                'description': 'Removes a country rate',
                'params': ['csrf_token'],
                'example_link': None
            },
            {
                'method': 'GET',
                'endpoint': '/admin/tickets',
                'description': 'Views all support tickets',
                'params': [],
                'example_link': f'{base_url}/admin/tickets'
            },
            {
                'method': 'GET',
                'endpoint': '/admin/tickets/<ticket_id>',
                'description': 'Views a specific ticket',
                'params': [],
                'example_link': f'{base_url}/admin/tickets/123'
            },
            {
                'method': 'POST',
                'endpoint': '/admin/tickets/reply/<ticket_id>',
                'description': 'Replies to a support ticket',
                'params': ['message', 'csrf_token'],
                'example_link': None
            },
            {
                'method': 'GET',
                'endpoint': '/admin/publisher-activity',
                'description': 'Displays publisher activity dashboard',
                'params': [],
                'example_link': f'{base_url}/admin/publisher-activity'
            },
            {
                'method': 'GET',
                'endpoint': '/admin/referral-settings',
                'description': 'Manages referral system settings',
                'params': [],
                'example_link': f'{base_url}/admin/referral-settings'
            },
            {
                'method': 'POST',
                'endpoint': '/admin/referral-settings/update',
                'description': 'Updates referral system settings',
                'params': ['enabled', 'reward_amount', 'csrf_token'],
                'example_link': None
            },
            {
                'method': 'GET',
                'endpoint': '/admin/referrals',
                'description': 'Lists all referral relationships',
                'params': [],
                'example_link': f'{base_url}/admin/referrals'
            },
        ],
    }
    
    return await render_template('admin_api_docs.html', 
                                  active_page='api_docs',
                                  api_endpoints=api_endpoints)
