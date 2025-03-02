import discord
import asyncio
from discord.ext import commands
import logging
import os
import re
from audit_service import AuditService
from audit_message import send_audit_status
from config import DISCORD_TOKEN, CHANNEL_ID
import pandas as pd
import time

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# 봇 설정
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# AuditService 인스턴스
audit_service = AuditService()

@bot.event
async def on_ready():
    logger.info(f'{bot.user}이 준비되었습니다!')
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.send(f'{bot.user}이 준비되었습니다!')

@bot.command(name='audit')
async def audit_command(ctx, *args):
    if not ctx.channel.id == CHANNEL_ID:
        await ctx.send("이 명령어는 지정된 채널에서만 사용할 수 있습니다.")
        return

    use_ai = False
    if args and args[-1] == '--use-ai':
        use_ai = True
        args = args[:-1]

    if not args:
        await ctx.send("프로젝트 ID를 입력해주세요. 예: !audit 20180076")
        return

    command = args[0].lower()

    if command == 'all':
        try:
            await send_audit_status(ctx, "🔍 audit_targets_new.csv에 있는 모든 프로젝트 감사를 시작합니다...")
            csv_path = os.path.join('static', 'data', 'audit_targets_new.csv')
            if not os.path.exists(csv_path):
                await ctx.send(f"❌ 오류 발생: CSV 파일을 찾을 수 없습니다: {csv_path}")
                logger.error(f"CSV file not found: {csv_path}")
                return

            df = pd.read_csv(csv_path, encoding='utf-8-sig')
            total_projects = len(df)

            if total_projects == 0:
                await ctx.send("❌ 오류 발생: audit_targets_new.csv에 프로젝트가 없습니다.")
                logger.error("No projects found in audit_targets_new.csv")
                return

            await send_audit_status(ctx, f"📊 총 {total_projects}개 프로젝트를 처리합니다...")

            # CSV 파일의 열 이름 확인 및 로깅
            logger.info(f"CSV columns: {df.columns.tolist()}")
            
            # 각 프로젝트 감사 수행
            project_ids = []
            department_codes = []
            start_time = time.time()
            
            for idx, row in df.iterrows():
                # Depart_ProjectID 열 확인
                if 'Depart_ProjectID' in df.columns:
                    project_id_value = str(row['Depart_ProjectID']).strip()
                    logger.info(f"Processing Depart_ProjectID: {project_id_value}")
                    
                    # 부서코드_C사업코드 형식 파싱
                    match = re.match(r'(\d{5})_C(\d+)$', project_id_value)
                    if match:
                        department_code = match.group(1)  # 부서코드 (이미 5자리)
                        project_id = match.group(2)  # 사업코드
                        logger.info(f"Successfully parsed: department_code={department_code}, project_id={project_id}")
                    else:
                        # 다른 형식 시도 (부서코드_사업코드)
                        parts = project_id_value.split('_')
                        if len(parts) == 2:
                            department_code = re.sub(r'[^0-9]', '', parts[0]).zfill(5)
                            project_id = re.sub(r'[^0-9]', '', parts[1])
                            logger.info(f"Parsed from split: department_code={department_code}, project_id={project_id}")
                        else:
                            # 파싱 실패 시
                            project_id = re.sub(r'[^0-9]', '', project_id_value)
                            department_code = None
                            logger.warning(f"Failed to parse Depart_ProjectID: {project_id_value}, using project_id={project_id}")
                else:
                    # 기존 project_id 열 찾기
                    project_id_col = next((col for col in ['project_id', 'ProjectID', '사업코드', 'projectId'] 
                                        if col in df.columns), None)
                    if not project_id_col:
                        error_msg = "No valid project_id column found in CSV"
                        logger.error(error_msg)
                        await send_audit_status(ctx, f"❌ 오류 발생: {error_msg}")
                        return
                    
                    project_id = re.sub(r'[^0-9]', '', str(row[project_id_col]))
                    department_code = None
                    logger.info(f"Using project_id from {project_id_col}: {project_id}")

                # 부서 코드가 없는 경우 department 열에서 확인
                if department_code is None:
                    for dept_col in ['department_code', 'Depart', '부서코드']:
                        if dept_col in df.columns and pd.notna(row[dept_col]):
                            department_code = str(row[dept_col]).zfill(5)
                            logger.info(f"Found department_code in {dept_col}: {department_code}")
                            break

                # 최종 확인 로그
                logger.info(f"Row {idx + 1}: Final values - project_id={project_id}, department_code={department_code}")

                if not project_id:
                    logger.warning(f"Skipping row {idx + 1}: Invalid project_id")
                    continue

                project_ids.append(project_id)
                department_codes.append(department_code)
                progress = f"({idx + 1}/{total_projects})"

                try:
                    logger.info(f"Starting audit for project_id={project_id}, department_code={department_code}")
                    await audit_service.audit_project(project_id, department_code, use_ai, ctx)
                    await send_audit_status(ctx, f"✅ 프로젝트 {project_id} 감사 완료 {progress}")
                except Exception as e:
                    error_msg = f"프로젝트 {project_id} 처리 중 오류 발생: {str(e)}"
                    logger.error(error_msg)
                    await send_audit_status(ctx, f"❌ {error_msg} {progress}")

            await send_audit_status(ctx, f"\n=== 모든 프로젝트 감사 완료 ({time.time() - start_time:.2f}초) ===")
            logger.info(f"모든 프로젝트 감사 완료, 총 소요 시간: {time.time() - start_time:.2f}초")

        except Exception as e:
            error_msg = f"모든 프로젝트 감사 처리 중 오류 발생: {str(e)}"
            logger.error(error_msg)
            await send_audit_status(ctx, f"❌ 오류 발생: {error_msg}")
    
    else:
        project_id = re.sub(r'[^0-9]', '', command)
        if not project_id:
            await ctx.send("유효한 프로젝트 ID를 입력해주세요. 예: !audit 20180076")
            return

        department_code = None
        if len(args) > 1:
            department_code = args[1].zfill(5) if args[1].isdigit() else None

        try:
            await audit_service.audit_project(project_id, department_code, use_ai, ctx)
            await ctx.send(f"✅ 프로젝트 {project_id} 감사 완료")
        except Exception as e:
            error_msg = f"프로젝트 {project_id} 처리 중 오류 발생: {str(e)}"
            logger.error(error_msg)
            await ctx.send(f"❌ 오류 발생: {error_msg}")

@bot.command(name='status')
async def status_command(ctx):
    if not ctx.channel.id == CHANNEL_ID:
        await ctx.send("이 명령어는 지정된 채널에서만 사용할 수 있습니다.")
        return
    await ctx.send("현재 봇 상태: 정상 작동 중")

async def main():
    try:
        await bot.start(DISCORD_TOKEN)
    except KeyboardInterrupt:
        await audit_service.close()
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main()) 