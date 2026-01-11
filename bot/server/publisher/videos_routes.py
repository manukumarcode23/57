from quart import Blueprint, request, render_template, redirect, session, jsonify
from bot.database import AsyncSessionLocal
from bot.models import File, PublisherImpression, AccessLog, Settings, CountryRate
from bot.server.publisher.utils import require_publisher
from bot.server.security import csrf_protect
from bot.config import Server
from sqlalchemy import select, and_, func, delete
from datetime import datetime, date, timedelta
import logging

bp = Blueprint('publisher_videos', __name__)
logger = logging.getLogger('bot.server')

@bp.route('/videos')
@require_publisher
async def videos():
    from_date = request.args.get('from_date', '')
    to_date = request.args.get('to_date', '')
    
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(File).where(File.publisher_id == session['publisher_id'])
        )
        
        query = select(File).where(File.publisher_id == session['publisher_id'])
        
        if from_date:
            try:
                from_datetime = datetime.strptime(from_date, '%Y-%m-%d')
                query = query.where(File.created_at >= from_datetime)
            except ValueError:
                pass
        
        if to_date:
            try:
                to_datetime = datetime.strptime(to_date, '%Y-%m-%d')
                to_datetime = to_datetime.replace(hour=23, minute=59, second=59)
                query = query.where(File.created_at <= to_datetime)
            except ValueError:
                pass
        
        result = await db_session.execute(query.order_by(File.created_at.desc()))
        files = result.scalars().all()
        
        total_files = len(files)
        
        date_counts = {}
        for file in files:
            file_date = file.created_at.date().isoformat()
            date_counts[file_date] = date_counts.get(file_date, 0) + 1
        
        chart_labels = sorted(date_counts.keys())
        chart_data = [date_counts[label] for label in chart_labels]
        
    return await render_template('publisher_videos.html', 
                                  active_page='videos',
                                  email=session['publisher_email'],
                                  files=files,
                                  total_files=total_files,
                                  from_date=from_date,
                                  to_date=to_date,
                                  chart_labels=chart_labels,
                                  chart_data=chart_data,
                                  base_url=Server.BASE_URL)

@bp.route('/statistics')
@require_publisher
async def statistics():
    file_ids_str = request.args.get('file_ids', '')
    
    if not file_ids_str:
        return redirect('/publisher/videos')
    
    try:
        file_ids = [int(fid) for fid in file_ids_str.split(',') if fid.strip()]
    except ValueError as e:
        logger.warning(f"Invalid file_ids parameter from user {session.get('publisher_email', 'unknown')}: {file_ids_str}, error: {e}")
        return redirect('/publisher/videos')
    
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(File).where(
                and_(
                    File.id.in_(file_ids),
                    File.publisher_id == session['publisher_id']
                )
            )
        )
        files = result.scalars().all()
        
        if not files:
            return redirect('/publisher/videos')
        
        settings_result = await db_session.execute(select(Settings))
        settings = settings_result.scalar_one_or_none()
        default_impression_rate = settings.impression_rate if settings else 0.0
        
        files_stats = []
        
        for file in files:
            total_impressions_result = await db_session.execute(
                select(func.count(PublisherImpression.id)).where(
                    PublisherImpression.hash_id == file.access_code
                )
            )
            total_impressions = total_impressions_result.scalar() or 0
            
            impressions_by_date_result = await db_session.execute(
                select(
                    PublisherImpression.impression_date,
                    func.count(PublisherImpression.id).label('count'),
                    PublisherImpression.country_code
                ).where(
                    PublisherImpression.hash_id == file.access_code
                ).group_by(
                    PublisherImpression.impression_date,
                    PublisherImpression.country_code
                ).order_by(
                    PublisherImpression.impression_date.desc()
                )
            )
            impressions_by_date_raw = impressions_by_date_result.all()
            
            country_rates_result = await db_session.execute(
                select(CountryRate).where(CountryRate.is_active == True)
            )
            country_rates = {cr.country_code: cr.impression_rate for cr in country_rates_result.scalars().all()}
            
            impressions_by_date = {}
            earnings_by_date = {}
            for row in impressions_by_date_raw:
                date_str = str(row.impression_date)
                impression_rate = country_rates.get(row.country_code, default_impression_rate)
                
                try:
                    count_value = int(row[1])  # row.count is the second column (index 1)
                except (ValueError, TypeError) as e:
                    logger.error(f"Invalid count value in database for file {file.access_code}: {row[1]}, error: {e}")
                    count_value = 0  # Use default value
                
                impressions_by_date[date_str] = impressions_by_date.get(date_str, 0) + count_value
                earnings_by_date[date_str] = earnings_by_date.get(date_str, 0.0) + (count_value * impression_rate)
            
            total_earnings = sum(earnings_by_date.values())
            
            total_downloads_result = await db_session.execute(
                select(func.count(AccessLog.id)).where(
                    and_(
                        AccessLog.file_id == file.id,
                        AccessLog.success == True
                    )
                )
            )
            total_downloads = total_downloads_result.scalar() or 0
            
            downloads_by_date_result = await db_session.execute(
                select(
                    func.date(AccessLog.access_time).label('date'),
                    func.count(AccessLog.id).label('count')
                ).where(
                    and_(
                        AccessLog.file_id == file.id,
                        AccessLog.success == True
                    )
                ).group_by(
                    func.date(AccessLog.access_time)
                ).order_by(
                    func.date(AccessLog.access_time).desc()
                )
            )
            downloads_by_date = {str(row.date): row.count for row in downloads_by_date_result.all()}
            
            all_dates = set(list(impressions_by_date.keys()) + list(downloads_by_date.keys()))
            if all_dates:
                date_objects = [datetime.strptime(d, '%Y-%m-%d').date() for d in all_dates]
                min_date = min(date_objects)
                max_date = max(date_objects)
            else:
                max_date = date.today()
                min_date = max_date - timedelta(days=30)
            
            dates = []
            current = min_date
            while current <= max_date:
                dates.append(current.isoformat())
                current += timedelta(days=1)
            
            chart_labels = dates
            chart_impressions = [impressions_by_date.get(d, 0) for d in dates]
            chart_earnings = [earnings_by_date.get(d, 0.0) for d in dates]
            chart_downloads = [downloads_by_date.get(d, 0) for d in dates]
            
            files_stats.append({
                'file': file,
                'total_impressions': total_impressions,
                'total_earnings': total_earnings,
                'total_downloads': total_downloads,
                'chart_labels': chart_labels,
                'chart_impressions': chart_impressions,
                'chart_earnings': chart_earnings,
                'chart_downloads': chart_downloads
            })
    
    return await render_template('publisher_statistics.html',
                                  active_page='videos',
                                  email=session['publisher_email'],
                                  files_stats=files_stats,
                                  base_url=Server.BASE_URL)

@bp.route('/delete-video/<int:file_id>', methods=['POST'])
@require_publisher
@csrf_protect
async def delete_video(file_id):
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(File).where(
                    and_(
                        File.id == file_id,
                        File.publisher_id == session['publisher_id']
                    )
                )
            )
            file_record = result.scalar_one_or_none()
            
            if not file_record:
                return jsonify({'status': 'error', 'message': 'File not found or unauthorized'}), 404
            
            filename = file_record.filename
            access_code = file_record.access_code
            
            stmt = delete(File).where(
                and_(
                    File.id == file_id,
                    File.publisher_id == session['publisher_id']
                )
            )
            await db_session.execute(stmt)
            await db_session.commit()
            
            logger.info(f"File deleted by publisher {session['publisher_email']}: {filename}, hash_id: {access_code}")
            
            return jsonify({'status': 'success', 'message': 'Video deleted successfully'}), 200
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error deleting file: {e}")
            return jsonify({'status': 'error', 'message': 'Failed to delete video'}), 500

@bp.route('/update-video-description', methods=['POST'])
@require_publisher
@csrf_protect
async def update_video_description():
    data = await request.form
    file_id = data.get('file_id')
    description = data.get('description', '').strip()
    
    if not file_id:
        return jsonify({'status': 'error', 'message': 'File ID is required'}), 400
    
    try:
        file_id = int(file_id)
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid file ID'}), 400
    
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(File).where(
                    and_(
                        File.id == file_id,
                        File.publisher_id == session['publisher_id']
                    )
                )
            )
            file_record = result.scalar_one_or_none()
            
            if not file_record:
                return jsonify({'status': 'error', 'message': 'File not found or unauthorized'}), 404
            
            file_record.custom_description = description if description else None
            await db_session.commit()
            
            logger.info(f"Description updated for file {file_record.filename} by publisher {session['publisher_email']}")
            
            return jsonify({'status': 'success', 'message': 'Description updated successfully'}), 200
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error updating video description: {e}")
            return jsonify({'status': 'error', 'message': 'Failed to update description'}), 500
