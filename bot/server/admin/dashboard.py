from quart import Blueprint, render_template, request, redirect
from bot.database import AsyncSessionLocal
from bot.models import Publisher, File, Settings, WithdrawalRequest, LinkTransaction, PublisherImpression, Subscription, Ticket, Referral, ReferralCode, AdNetwork, Bot
from sqlalchemy import select, func, desc
from datetime import date, timedelta, datetime
from .utils import require_admin
import psutil

bp = Blueprint('admin_dashboard', __name__)

@bp.route('/dashboard')
@require_admin
async def dashboard():
    async with AsyncSessionLocal() as db_session:
        today = date.today()
        first_day_of_month = date(today.year, today.month, 1)
        
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        disk = psutil.disk_usage('/')
        disk_total_gb = disk.total / (1024 ** 3)
        disk_used_gb = disk.used / (1024 ** 3)
        disk_free_gb = disk.free / (1024 ** 3)
        disk_percent = disk.percent
        
        max_usage = max(cpu_percent, memory_percent, disk_percent)
        server_health = max(0, 100 - max_usage)
        
        publisher_count = await db_session.scalar(
            select(func.count(Publisher.id))
        )
        active_publisher_count = await db_session.scalar(
            select(func.count(Publisher.id))
            .where(Publisher.is_active == True)
        )
        file_count = await db_session.scalar(
            select(func.count(File.id))
        )
        
        total_links = await db_session.scalar(
            select(func.count(LinkTransaction.id))
        )
        
        today_links = await db_session.scalar(
            select(func.count(LinkTransaction.id))
            .where(func.date(LinkTransaction.created_at) == today)
        )
        
        month_links = await db_session.scalar(
            select(func.count(LinkTransaction.id))
            .where(func.date(LinkTransaction.created_at) >= first_day_of_month)
        )
        
        total_impressions = await db_session.scalar(
            select(func.count(PublisherImpression.id))
        )
        
        today_impressions = await db_session.scalar(
            select(func.count(PublisherImpression.id))
            .where(PublisherImpression.impression_date == today)
        )
        
        month_impressions = await db_session.scalar(
            select(func.count(PublisherImpression.id))
            .where(PublisherImpression.impression_date >= first_day_of_month)
        )
        
        total_balance = await db_session.scalar(
            select(func.sum(Publisher.balance))
        ) or 0
        
        settings_result = await db_session.execute(select(Settings))
        settings = settings_result.scalar_one_or_none()
        impression_rate = settings.impression_rate if settings else 0
        
        estimated_total_revenue = (total_impressions or 0) * impression_rate
        today_revenue = (today_impressions or 0) * impression_rate
        month_revenue = (month_impressions or 0) * impression_rate
        
        pending_withdrawals = await db_session.scalar(
            select(func.count(WithdrawalRequest.id))
            .where(WithdrawalRequest.status == 'pending')
        )
        
        top_files_result = await db_session.execute(
            select(
                File.filename,
                File.access_code,
                func.count(PublisherImpression.id).label('impression_count')
            )
            .join(PublisherImpression, PublisherImpression.hash_id == File.access_code)
            .group_by(File.id, File.filename, File.access_code)
            .order_by(desc('impression_count'))
            .limit(5)
        )
        top_files = top_files_result.all()
        
        result = await db_session.execute(
            select(Publisher).order_by(Publisher.created_at.desc()).limit(5)
        )
        recent_publishers = result.scalars().all()
        
        seven_days_ago = today - timedelta(days=7)
        active_users = await db_session.scalar(
            select(func.count(func.distinct(PublisherImpression.android_id)))
            .where(PublisherImpression.impression_date >= seven_days_ago)
        ) or 0
        
        total_subscriptions = await db_session.scalar(
            select(func.count(Subscription.id))
        ) or 0
        
        now = datetime.now()
        active_subscriptions = await db_session.scalar(
            select(func.count(Subscription.id))
            .where(Subscription.status == 'active')
            .where(Subscription.expires_at > now)
        ) or 0
        
        completed_subscriptions = await db_session.scalar(
            select(func.count(Subscription.id))
            .where(Subscription.status == 'completed')
        ) or 0
        
        pending_payments = await db_session.scalar(
            select(func.count(Subscription.id))
            .where(Subscription.status == 'pending')
        ) or 0
        
        today_subscription_revenue = await db_session.scalar(
            select(func.sum(Subscription.amount))
            .where(Subscription.status == 'completed')
            .where(func.date(Subscription.created_at) == today)
        ) or 0
        
        month_subscription_revenue = await db_session.scalar(
            select(func.sum(Subscription.amount))
            .where(Subscription.status == 'completed')
            .where(func.date(Subscription.created_at) >= first_day_of_month)
        ) or 0
        
        total_subscription_revenue = await db_session.scalar(
            select(func.sum(Subscription.amount))
            .where(Subscription.status == 'completed')
        ) or 0
        
        total_tickets = await db_session.scalar(
            select(func.count(Ticket.id))
        ) or 0
        
        open_tickets = await db_session.scalar(
            select(func.count(Ticket.id))
            .where(Ticket.status == 'open')
        ) or 0
        
        pending_tickets = await db_session.scalar(
            select(func.count(Ticket.id))
            .where(Ticket.status == 'pending')
        ) or 0
        
        total_referrals = await db_session.scalar(
            select(func.count(Referral.id))
        ) or 0
        
        total_referral_earnings = await db_session.scalar(
            select(func.sum(ReferralCode.total_earnings))
        ) or 0
        
        active_ad_networks = await db_session.scalar(
            select(func.count(AdNetwork.id))
            .where(AdNetwork.status == 'active')
        ) or 0
        
        active_bots = await db_session.scalar(
            select(func.count(Bot.id))
            .where(Bot.is_active == True)
        ) or 0
        
        today_files_uploaded = await db_session.scalar(
            select(func.count(File.id))
            .where(func.date(File.created_at) == today)
        ) or 0
        
    return await render_template('admin_dashboard.html', 
                                  active_page='dashboard',
                                  publisher_count=publisher_count or 0,
                                  active_publisher_count=active_publisher_count or 0,
                                  file_count=file_count or 0,
                                  total_links=total_links or 0,
                                  today_links=today_links or 0,
                                  month_links=month_links or 0,
                                  total_impressions=total_impressions or 0,
                                  today_impressions=today_impressions or 0,
                                  month_impressions=month_impressions or 0,
                                  recent_publishers=recent_publishers,
                                  cpu_percent=round(cpu_percent, 1),
                                  memory_percent=round(memory_percent, 1),
                                  disk_total_gb=round(disk_total_gb, 2),
                                  disk_used_gb=round(disk_used_gb, 2),
                                  disk_free_gb=round(disk_free_gb, 2),
                                  disk_percent=round(disk_percent, 1),
                                  server_health=round(server_health, 1),
                                  total_balance=round(total_balance, 2),
                                  estimated_total_revenue=round(estimated_total_revenue, 2),
                                  today_revenue=round(today_revenue, 2),
                                  month_revenue=round(month_revenue, 2),
                                  pending_withdrawals=pending_withdrawals or 0,
                                  top_files=top_files,
                                  active_users=active_users,
                                  total_subscriptions=total_subscriptions,
                                  active_subscriptions=active_subscriptions,
                                  completed_subscriptions=completed_subscriptions,
                                  pending_payments=pending_payments,
                                  today_subscription_revenue=round(today_subscription_revenue, 2),
                                  month_subscription_revenue=round(month_subscription_revenue, 2),
                                  total_subscription_revenue=round(total_subscription_revenue, 2),
                                  total_tickets=total_tickets,
                                  open_tickets=open_tickets,
                                  pending_tickets=pending_tickets,
                                  total_referrals=total_referrals,
                                  total_referral_earnings=round(total_referral_earnings, 2),
                                  active_ad_networks=active_ad_networks,
                                  active_bots=active_bots,
                                  today_files_uploaded=today_files_uploaded)

@bp.route('/terabox-settings', methods=['GET', 'POST'])
@require_admin
async def terabox_settings():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Settings))
        settings = result.scalar_one_or_none()
        
        if request.method == 'POST':
            data = await request.form
            domains = data.get('domains', '').strip()
            terabox_api_url = data.get('terabox_api_url', '').strip()
            if settings:
                settings.terabox_domains = domains
                settings.terabox_api_key = terabox_api_url
                await session.commit()
                return redirect('/admin/terabox-settings')

        domains_list = settings.terabox_domains.split(',') if settings and settings.terabox_domains else []
        return await render_template('admin_terabox.html', 
                                   active_page='terabox', 
                                   domains=domains_list, 
                                   raw_domains=settings.terabox_domains if settings else "",
                                   terabox_api_url=settings.terabox_api_key if settings else "")
