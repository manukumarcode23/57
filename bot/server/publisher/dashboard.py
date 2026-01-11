from quart import Blueprint, render_template, session
from bot.database import AsyncSessionLocal
from bot.models import File, Publisher, PublisherImpression, ImpressionAdjustment, Settings, PremiumLinkEarning
from bot.server.publisher.utils import require_publisher
from sqlalchemy import select, and_, func
from datetime import date, timedelta

bp = Blueprint('publisher_dashboard', __name__)

@bp.route('/dashboard')
@require_publisher
async def dashboard():
    today = date.today()
    
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(Publisher).where(Publisher.id == session['publisher_id'])
        )
        publisher = result.scalar_one_or_none()
        
        total_files_result = await db_session.execute(
            select(func.count(File.id)).where(File.publisher_id == session['publisher_id'])
        )
        total_files = total_files_result.scalar() or 0
        
        today_files_result = await db_session.execute(
            select(func.count(File.id)).where(
                and_(
                    File.publisher_id == session['publisher_id'],
                    func.date(File.created_at) == today
                )
            )
        )
        today_files = today_files_result.scalar() or 0
        
        total_impressions_result = await db_session.execute(
            select(func.count(PublisherImpression.id)).where(
                PublisherImpression.publisher_id == session['publisher_id']
            )
        )
        total_impressions = total_impressions_result.scalar() or 0
        
        # Add manual impression adjustments from admin
        adjustment_total = await db_session.scalar(
            select(func.sum(ImpressionAdjustment.amount)).where(
                ImpressionAdjustment.publisher_id == session['publisher_id'],
                ImpressionAdjustment.adjustment_type == 'add'
            )
        )
        manual_adjustments = int(adjustment_total) if adjustment_total else 0
        total_impressions += manual_adjustments
        
        today_impressions_result = await db_session.execute(
            select(func.count(PublisherImpression.id)).where(
                and_(
                    PublisherImpression.publisher_id == session['publisher_id'],
                    PublisherImpression.impression_date == today
                )
            )
        )
        today_impressions = today_impressions_result.scalar() or 0
        
        files_result = await db_session.execute(
            select(
                func.date(File.created_at).label('date'),
                func.count(File.id).label('count')
            ).where(
                File.publisher_id == session['publisher_id']
            ).group_by(
                func.date(File.created_at)
            ).order_by(
                func.date(File.created_at).desc()
            ).limit(30)
        )
        files_by_date = {str(row.date): int(row[1]) for row in files_result.all()}
        
        impressions_result = await db_session.execute(
            select(
                PublisherImpression.impression_date,
                func.count(PublisherImpression.id).label('count')
            ).where(
                PublisherImpression.publisher_id == session['publisher_id']
            ).group_by(
                PublisherImpression.impression_date
            ).order_by(
                PublisherImpression.impression_date.desc()
            ).limit(30)
        )
        impressions_by_date = {str(row.impression_date): int(row[1]) for row in impressions_result.all()}
        
        settings_result = await db_session.execute(select(Settings))
        settings = settings_result.scalar_one_or_none()
        impression_rate = settings.impression_rate if settings else 0.0
        
        today_earnings = today_impressions * impression_rate
        total_earnings = total_impressions * impression_rate
        
        total_premium_earnings_result = await db_session.execute(
            select(func.coalesce(func.sum(PremiumLinkEarning.earning_amount), 0)).where(
                PremiumLinkEarning.publisher_id == session['publisher_id']
            )
        )
        total_premium_earnings = float(total_premium_earnings_result.scalar() or 0.0)
        
        today_premium_earnings_result = await db_session.execute(
            select(func.coalesce(func.sum(PremiumLinkEarning.earning_amount), 0)).where(
                and_(
                    PremiumLinkEarning.publisher_id == session['publisher_id'],
                    PremiumLinkEarning.earning_date == today
                )
            )
        )
        today_premium_earnings = float(today_premium_earnings_result.scalar() or 0.0)
        
        total_premium_count_result = await db_session.execute(
            select(func.count(PremiumLinkEarning.id)).where(
                PremiumLinkEarning.publisher_id == session['publisher_id']
            )
        )
        total_premium_count = total_premium_count_result.scalar() or 0
        
        today_premium_count_result = await db_session.execute(
            select(func.count(PremiumLinkEarning.id)).where(
                and_(
                    PremiumLinkEarning.publisher_id == session['publisher_id'],
                    PremiumLinkEarning.earning_date == today
                )
            )
        )
        today_premium_count = today_premium_count_result.scalar() or 0
        
        dates = [(today - timedelta(days=i)) for i in range(29, -1, -1)]
        dates_str = [d.isoformat() for d in dates]
        
        chart_labels = [d.strftime('%b %d') for d in dates]
        chart_files_data = [files_by_date.get(d_str, 0) for d_str in dates_str]
        chart_impressions_data = [impressions_by_date.get(d_str, 0) for d_str in dates_str]
        chart_earnings_data = [impressions_by_date.get(d_str, 0) * impression_rate for d_str in dates_str]
        
    return await render_template('publisher_dashboard.html', 
                                  active_page='dashboard',
                                  email=session['publisher_email'],
                                  balance=publisher.balance if publisher else 0.0,
                                  total_files=total_files,
                                  today_files=today_files,
                                  total_impressions=total_impressions,
                                  today_impressions=today_impressions,
                                  today_earnings=today_earnings,
                                  total_earnings=total_earnings,
                                  impression_rate=impression_rate,
                                  total_premium_earnings=total_premium_earnings,
                                  today_premium_earnings=today_premium_earnings,
                                  total_premium_count=total_premium_count,
                                  today_premium_count=today_premium_count,
                                  chart_labels=chart_labels,
                                  chart_files_data=chart_files_data,
                                  chart_impressions_data=chart_impressions_data,
                                  chart_earnings_data=chart_earnings_data)
