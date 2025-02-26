@bot.command(name='audit')
async def audit(ctx, project_id: str = None, use_ai: bool = False):
    """프로젝트 감사 명령어 처리"""
    print(f"\n[DEBUG] Audit command received")
    
    try:
        if project_id:
            # 단일 프로젝트 감사
            print(f"[DEBUG] Starting audit for project {project_id}")
            await ctx.send(f"🔍 프로젝트 {project_id} 감사를 시작합니다...")
            result = await audit_service.audit_project(project_id, use_ai=use_ai)
            
            if 'error' in result:
                await ctx.send(f"❌ Error: {result['error']}")
                return
                
            await audit_service.send_to_discord(result, ctx=ctx)
            
        else:
            # 전체 프로젝트 감사
            await ctx.send("📋 전체 프로젝트 감사를 시작합니다...")
            
            try:
                # project_list.csv 읽기
                df = pd.read_csv(PROJECT_LIST_CSV)
                total_projects = len(df)
                await ctx.send(f"총 {total_projects}개의 프로젝트를 감사합니다.")
                
                success_count = 0
                error_count = 0
                
                for index, row in df.iterrows():
                    current_project_id = str(row['project_id'])
                    try:
                        await ctx.send(f"🔍 프로젝트 {current_project_id} 감사 중... ({index + 1}/{total_projects})")
                        result = await audit_service.audit_project(current_project_id, use_ai=use_ai)
                        
                        if 'error' in result:
                            error_count += 1
                            await ctx.send(f"❌ {current_project_id} 감사 실패: {result['error']}")
                        else:
                            success_count += 1
                            await audit_service.send_to_discord(result, ctx=ctx)
                            
                    except Exception as e:
                        error_count += 1
                        await ctx.send(f"❌ {current_project_id} 감사 중 오류 발생: {str(e)}")
                    
                    # 각 프로젝트 사이에 잠시 대기 (API 제한 고려)
                    await asyncio.sleep(1)
                
                # 최종 결과 보고
                summary = f"""
📊 감사 완료 보고서
------------------------
✅ 성공: {success_count}개
❌ 실패: {error_count}개
📋 총 처리: {total_projects}개
------------------------
"""
                await ctx.send(summary)
                
            except Exception as e:
                await ctx.send(f"❌ 전체 프로젝트 감사 중 오류 발생: {str(e)}")
                print(f"[DEBUG] Batch audit error: {str(e)}")
                print(f"[DEBUG] Traceback: {traceback.format_exc()}")
    
    except Exception as e:
        error_message = f"감사 처리 중 오류 발생: {str(e)}"
        print(f"[DEBUG] Exception occurred: {str(e)}")
        print(f"[DEBUG] Traceback: {traceback.format_exc()}")
        await ctx.send(error_message) 