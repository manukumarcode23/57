from quart import Blueprint
from . import dashboard
from . import publishers_routes
from . import ads_routes
from . import settings_routes
from . import withdrawals_routes
from . import bots_routes
from . import country_rates_routes
from . import tickets_routes
from . import activity_routes
from . import referral_routes
from . import api_docs_routes
from . import api_keys_routes
from . import account_routes
from . import subscription_routes
from . import payment_routes
from . import web_subscription_routes
from . import ipqs_keys_routes
from . import r2_keys_routes

bp = Blueprint('admin', __name__, url_prefix='/admin')

bp.register_blueprint(dashboard.bp)
bp.register_blueprint(publishers_routes.bp)
bp.register_blueprint(ads_routes.bp)
bp.register_blueprint(settings_routes.bp)
bp.register_blueprint(withdrawals_routes.bp)
bp.register_blueprint(bots_routes.bp)
bp.register_blueprint(country_rates_routes.bp)
bp.register_blueprint(tickets_routes.bp)
bp.register_blueprint(activity_routes.bp)
bp.register_blueprint(referral_routes.bp)
bp.register_blueprint(api_docs_routes.bp)
bp.register_blueprint(api_keys_routes.bp)
bp.register_blueprint(account_routes.bp)
bp.register_blueprint(subscription_routes.bp)
bp.register_blueprint(payment_routes.bp)
bp.register_blueprint(web_subscription_routes.bp)
bp.register_blueprint(ipqs_keys_routes.bp)
bp.register_blueprint(r2_keys_routes.bp)
