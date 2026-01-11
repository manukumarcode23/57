from quart import Blueprint, request, render_template, redirect
from bot.database import AsyncSessionLocal
from bot.models import CountryRate, Settings
from sqlalchemy import select, delete
from .utils import require_admin
from bot.server.security import csrf_protect, get_csrf_token

bp = Blueprint('admin_country_rates', __name__)

@bp.route('/country-rates')
@require_admin
async def country_rates():
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(CountryRate).order_by(CountryRate.country_name)
        )
        country_rates = result.scalars().all()
        
        settings_result = await db_session.execute(select(Settings))
        settings = settings_result.scalar_one_or_none()
        default_rate = settings.impression_rate if settings else 0.0
        
    csrf_token = get_csrf_token()
    return await render_template('admin_country_rates.html', 
                                  active_page='country_rates',
                                  country_rates=country_rates,
                                  default_rate=default_rate,
                                  csrf_token=csrf_token)

@bp.route('/country-rates/add', methods=['POST'])
@require_admin
@csrf_protect
async def add_country_rate():
    data = await request.form
    country_code = data.get('country_code', '').strip().upper()
    country_name = data.get('country_name', '').strip()
    impression_rate = data.get('impression_rate', '0')
    
    try:
        impression_rate = float(impression_rate)
    except ValueError:
        return redirect('/admin/country-rates?error=Invalid impression rate')
    
    async with AsyncSessionLocal() as db_session:
        try:
            existing_result = await db_session.execute(
                select(CountryRate).where(CountryRate.country_code == country_code)
            )
            existing = existing_result.scalar_one_or_none()
            
            if existing:
                return redirect('/admin/country-rates?error=Country code already exists')
            
            country_rate = CountryRate(
                country_code=country_code,
                country_name=country_name,
                impression_rate=impression_rate,
                is_active=True
            )
            
            db_session.add(country_rate)
            await db_session.commit()
            
            return redirect('/admin/country-rates')
            
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/country-rates?error=Failed to add country rate')

@bp.route('/country-rates/update/<int:rate_id>', methods=['POST'])
@require_admin
@csrf_protect
async def update_country_rate(rate_id):
    data = await request.form
    impression_rate = data.get('impression_rate', '0')
    
    try:
        impression_rate = float(impression_rate)
    except ValueError:
        return redirect('/admin/country-rates?error=Invalid impression rate')
    
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(CountryRate).where(CountryRate.id == rate_id)
            )
            country_rate = result.scalar_one_or_none()
            
            if country_rate:
                country_rate.impression_rate = impression_rate
                await db_session.commit()
            
            return redirect('/admin/country-rates')
            
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/country-rates?error=Failed to update country rate')

@bp.route('/country-rates/toggle/<int:rate_id>', methods=['POST'])
@require_admin
@csrf_protect
async def toggle_country_rate(rate_id):
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(CountryRate).where(CountryRate.id == rate_id)
            )
            country_rate = result.scalar_one_or_none()
            
            if country_rate:
                country_rate.is_active = not country_rate.is_active
                await db_session.commit()
            
            return redirect('/admin/country-rates')
            
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/country-rates')

@bp.route('/country-rates/delete/<int:rate_id>', methods=['POST'])
@require_admin
@csrf_protect
async def delete_country_rate(rate_id):
    async with AsyncSessionLocal() as db_session:
        try:
            stmt = delete(CountryRate).where(CountryRate.id == rate_id)
            await db_session.execute(stmt)
            await db_session.commit()
            
            return redirect('/admin/country-rates')
            
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/country-rates')
