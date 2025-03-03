# my_flask_app/audit_message.py

import discord
import aiohttp
from datetime import datetime
from config import DISCORD_WEBHOOK_URL
from config_assets import DOCUMENT_TYPES
import logging

logger = logging.getLogger(__name__)

async def send_audit_status_to_discord(ctx, message):
    """디스코드 채널에 감사 상태 메시지 전송"""
    try:
        if ctx and ctx.channel:
            await ctx.send(message)
            logger.info(f"Sent audit status to Discord channel: {message}")
    except Exception as e:
        logger.error(f"Error sending audit status to Discord channel: {str(e)}")

async def send_audit_to_discord(data):
    """디스코드 웹훅으로 감사 결과 전송"""
    if not DISCORD_WEBHOOK_URL:
        logger.warning("DISCORD_WEBHOOK_URL is not configured, skipping webhook send.")
        return

    try:
        async with aiohttp.ClientSession() as session:
            if isinstance(data, list):
                for item in data:
                    if 'error' not in item:
                        message = (
                            f"📋 **Project Audit Result**\n"
                            f"ID: {item.get('project_id', 'Unknown')}\n"
                            f"Department: {item.get('department', item.get('department_code', 'Unknown'))}\n"
                            f"Name: {item.get('project_name', f'Project {item.get('project_id', 'Unknown')}')}\n"
                            f"Status: {item.get('status', 'Unknown')}\n"  # Status 추가
                            f"Contractor: {item.get('contractor', 'Unknown')}\n"  # Contractor 추가
                            f"Path: {item.get('project_path', 'Unknown')}\n\n"
                            f"📑 Documents:\n"
                        )

                        found_docs = []
                        missing_docs = []
                        documents = item.get('documents', {})
                        for doc_type in documents.keys():
                            doc_name = DOCUMENT_TYPES.get(doc_type, {}).get('name', doc_type)  # DOC_TYPES → DOCUMENT_TYPES 수정
                            doc_info = documents.get(doc_type, {'exists': False, 'details': []})
                            if doc_info.get('exists', False):
                                count = len(doc_info.get('details', []))
                                found_docs.append(f"{doc_name} ({count}개)")
                            else:
                                missing_docs.append(f"{doc_name} (0개)")

                        if found_docs:
                            message += "✅ Found:\n- " + "\n- ".join(found_docs) + "\n\n"
                        if missing_docs:
                            message += "❌ Missing:\n- " + "\n- ".join(missing_docs) + "\n\n"

                        if 'ai_analysis' in item and item['ai_analysis']:
                            message += f"🤖 AI Analysis:\n{item['ai_analysis']}"

                        message += f"\n⏰ {item.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}"
                        async with session.post(DISCORD_WEBHOOK_URL, json={'content': message}, timeout=10) as response:
                            if response.status != 204:
                                logger.warning(f"Webhook response status: {response.status}")
                                print(f"Failed to send audit result to Discord webhook: {message}")
                    else:
                        message = (
                            f"❌ **Audit Error**\n"
                            f"Project ID: {item.get('project_id', 'Unknown')}\n"
                            f"Department: {item.get('department', item.get('department_code', 'Unknown'))}\n"
                            f"Error: {item['error']}\n"
                            f"⏰ {item.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}"
                        )
                        async with session.post(DISCORD_WEBHOOK_URL, json={'content': message}, timeout=10) as response:
                            if response.status != 204:
                                logger.warning(f"Webhook response status: {response.status}")
                                print(f"Failed to send audit error to Discord webhook: {message}")
            else:
                if 'error' not in data:
                    message = (
                        f"📋 **Project Audit Result**\n"
                        f"ID: {data.get('project_id', 'Unknown')}\n"
                        f"Department: {data.get('department', data.get('department_code', 'Unknown'))}\n"
                        f"Name: {data.get('project_name', f'Project {data.get('project_id', 'Unknown')}')}\n"
                        f"Status: {data.get('status', 'Unknown')}\n"  # Status 추가
                        f"Contractor: {data.get('contractor', 'Unknown')}\n"  # Contractor 추가
                        f"Path: {data.get('project_path', 'Unknown')}\n\n"
                        f"📑 Documents:\n"
                    )

                    found_docs = []
                    missing_docs = []
                    documents = data.get('documents', {})
                    for doc_type in documents.keys():
                        doc_name = DOCUMENT_TYPES.get(doc_type, {}).get('name', doc_type)  # DOC_TYPES → DOCUMENT_TYPES 수정
                        doc_info = documents.get(doc_type, {'exists': False, 'details': []})
                        if doc_info.get('exists', False):
                            count = len(doc_info.get('details', []))
                            found_docs.append(f"{doc_name} ({count}개)")
                        else:
                            missing_docs.append(f"{doc_name} (0개)")

                    if found_docs:
                        message += "✅ Found:\n- " + "\n- ".join(found_docs) + "\n\n"
                    if missing_docs:
                        message += "❌ Missing:\n- " + "\n- ".join(missing_docs) + "\n\n"

                    if 'ai_analysis' in data and data['ai_analysis']:
                        message += f"🤖 AI Analysis:\n{data['ai_analysis']}"

                    message += f"\n⏰ {data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}"
                    async with session.post(DISCORD_WEBHOOK_URL, json={'content': message}, timeout=10) as response:
                        if response.status != 204:
                            logger.warning(f"Webhook response status: {response.status}")
                            print(f"Failed to send audit result to Discord webhook: {message}")
                else:
                    message = (
                        f"❌ **Audit Error**\n"
                        f"Project ID: {data.get('project_id', 'Unknown')}\n"
                        f"Department: {data.get('department', data.get('department_code', 'Unknown'))}\n"
                        f"Status: {data.get('status', 'Unknown')}\n"  # Status 추가
                        f"Contractor: {data.get('contractor', 'Unknown')}\n"  # Contractor 추가
                        f"Error: {data['error']}\n"
                        f"⏰ {data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}"
                    )
                    async with session.post(DISCORD_WEBHOOK_URL, json={'content': message}, timeout=10) as response:
                        if response.status != 204:
                            logger.warning(f"Webhook response status: {response.status}")
                            print(f"Failed to send audit error to Discord webhook: {message}")

    except Exception as e:
        logger.error(f"Error sending audit to Discord webhook: {str(e)}")