from quart import Blueprint
from bot.server.publisher import dashboard, upload_routes, api_routes, videos_routes, withdrawal_routes, tickets_routes, referral_routes, settings_routes, descriptions_routes, subscription_routes

bp = Blueprint('publisher', __name__, url_prefix='/publisher')

bp.register_blueprint(dashboard.bp)
bp.register_blueprint(upload_routes.bp)
bp.register_blueprint(api_routes.bp)
bp.register_blueprint(videos_routes.bp)
bp.register_blueprint(withdrawal_routes.bp)
bp.register_blueprint(tickets_routes.bp)
bp.register_blueprint(referral_routes.bp)
bp.register_blueprint(settings_routes.bp)
bp.register_blueprint(descriptions_routes.bp)
bp.register_blueprint(subscription_routes.bp)
