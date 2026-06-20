"""
AI 生图端点（Phase 7）

路由列表：
  GET  /api/image-provider/status                          检查生图配置状态
  POST /api/projects/{project_id}/generate-image           AI生图完整链路
  POST /api/projects/{project_id}/generate-image/confirm  确认后回流知识库
  GET  /api/reference-images/vocabularies                  获取分类受控词表
  POST /api/projects/{project_id}/reference-images/classify 参考图分类
"""
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db, serialized_write
from app.json_safety import safe_json_dump, safe_json_parse

logger = logging.getLogger(__name__)
router = APIRouter()


# ──────────────────────────────────────────────────────────────
# 1. 配置状态检查
# ──────────────────────────────────────────────────────────────

@router.get("/image-provider/status")
async def image_provider_status():
    """检查生图配置状态（不暴露 Key 本身）"""
    from app.image_provider import ImageGenerationProvider

    provider = ImageGenerationProvider()
    return provider.get_status()


# ──────────────────────────────────────────────────────────────
# 2. AI 生图主链路
# ──────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/generate-image")
async def generate_image(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    AI 生图完整链路：
    读项目上下文 → DeepSeek 组提示词 → 生图 API → 存项目成果目录 → 返回成果卡
    成果卡状态为 pending，需用户确认后才回流知识库。
    """
    from app.image_provider import ImageGenerationProvider
    from app.models import AgentRun, Project
    from app.services import call_deepseek_text

    body = await request.json()
    user_description: str = body.get("description", "")
    custom_prompt: str = body.get("prompt", "")
    size: str = body.get("size", "1024x1024")
    style: str = body.get("style", "natural")

    if not user_description and not custom_prompt:
        return JSONResponse({"error": "请提供图片描述或提示词"}, status_code=400)

    # 检查生图配置
    provider = ImageGenerationProvider()
    if not provider.is_configured:
        return JSONResponse(
            {
                "error": "not_configured",
                "message": "AI生图未配置。请在 .env 文件中设置 IMAGE_API_KEY。",
                "config_guide": {
                    "required": ["IMAGE_API_KEY"],
                    "optional": [
                        "IMAGE_BASE_URL",
                        "IMAGE_MODEL",
                        "IMAGE_PROVIDER",
                        "IMAGE_OUTPUT_DIR",
                    ],
                    "default_provider": "huashu",
                    "default_base_url": "https://api.huashu.ai/v1",
                },
            },
            status_code=400,
        )

    # 获取项目上下文
    project = db.query(Project).filter_by(id=project_id).first()
    if not project:
        return JSONResponse({"error": "项目不存在"}, status_code=404)

    project_context = {
        "name": project.name,
        "city": getattr(project, "city", "") or "",
        "project_type": getattr(project, "project_type", "") or "",
    }

    # 组提示词（custom_prompt 优先；否则用 DeepSeek 扩写）
    if custom_prompt:
        final_prompt = custom_prompt
    else:
        try:
            compose_user_prompt = (
                f"项目：{project_context['name']}（{project_context['city']}，"
                f"{project_context['project_type']}）\n"
                f"用户描述：{user_description}\n"
                f"风格要求：{style}\n\n"
                f"请直接输出英文提示词（不要JSON包装、不要解释），200字以内："
            )
            compose_system_prompt = (
                "你是建筑效果图AI生图提示词专家。"
                "根据用户描述和项目背景，生成高质量的英文图像生成提示词。"
                "直接输出提示词文本，不要任何包装或解释。"
            )
            final_prompt = await call_deepseek_text(
                compose_user_prompt, compose_system_prompt
            )
            if not final_prompt or not final_prompt.strip():
                final_prompt = user_description
        except Exception as exc:  # noqa: BLE001
            logger.warning("Prompt composition failed, using raw description: %s", exc)
            final_prompt = user_description

    # 调用生图 API
    result = await provider.generate(
        prompt=final_prompt, size=size, style=style
    )

    if not result.success:
        status_code = 400 if result.error == "not_configured" else 500
        return JSONResponse(
            {
                "error": result.error,
                "message": result.metadata.get("message", "生图失败"),
                "prompt_used": result.prompt_used,
            },
            status_code=status_code,
        )

    # 保存图片到磁盘
    b64_data: str = result.metadata.get("b64_json", "")
    saved_path = provider.save_image(
        b64_data, project_id, filename_prefix="ai_gen"
    )

    if not saved_path:
        return JSONResponse({"error": "图片保存失败"}, status_code=500)

    # 构建成果卡（confirmed=False，用户确认后才入库）
    result_card = {
        "card_type": "ai_image_generation",
        "skill_name": "AI生图",
        "title": f"生图 - {user_description[:30] or final_prompt[:30]}",
        "status": "generated",
        "image_path": saved_path,
        "prompt_used": final_prompt,
        "user_description": user_description,
        "model": result.model,
        "size": size,
        "style": style,
        "project_context": project_context,
        "actions": ["view", "regenerate", "confirm_to_knowledge"],
        "confirmed": False,
    }

    # 记录 AgentRun
    with serialized_write():
        agent_run = AgentRun(
            project_id=project_id,
            agent_id="ai_image_generation",
            input_context=safe_json_dump(
                {"description": user_description, "prompt": final_prompt}
            ),
            output_json=safe_json_dump(result_card),
            status="completed",
        )
        db.add(agent_run)
        db.commit()

    return {"success": True, "result_card": result_card}


# ──────────────────────────────────────────────────────────────
# 3. 确认图片回流知识库
# ──────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/generate-image/confirm")
async def confirm_image_to_knowledge(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    用户确认后将生成图片信息回流知识库。
    未经确认的图片不入库（符合"不满意不入库"原则）。
    """
    from app.models import KnowledgeFile
    from app.security import PathValidationError, validate_path
    from app.config import settings

    body = await request.json()
    image_path: str = body.get("image_path", "")
    tags: list = body.get("tags", [])
    description: str = body.get("description", "")

    if not image_path:
        return JSONResponse({"error": "缺少图片路径"}, status_code=400)

    # 路径安全校验
    allowed_bases = [settings.data_dir_path, settings.upload_root_path]
    if settings.image_output_dir:
        allowed_bases.append(Path(settings.image_output_dir))

    try:
        validated = validate_path(image_path, allowed_bases=allowed_bases)
    except PathValidationError as exc:
        logger.warning("Path validation failed for image confirm: %s", exc)
        return JSONResponse({"error": f"路径校验失败: {exc}"}, status_code=400)

    if not validated.exists():
        return JSONResponse({"error": "图片文件不存在"}, status_code=404)

    # 回流知识库
    with serialized_write():
        kf = KnowledgeFile(
            filename=validated.name,
            filepath=str(validated),
            filetype="ai_generated_image",
            filesize=validated.stat().st_size,
            title=description[:100] if description else validated.stem,
            folder=f"ai-generated/{project_id}",
        )
        db.add(kf)
        db.commit()

    return {
        "success": True,
        "message": "图片已确认并回流知识库",
        "knowledge_file_name": validated.name,
    }


# ──────────────────────────────────────────────────────────────
# 4. 参考图受控词表
# ──────────────────────────────────────────────────────────────

@router.get("/reference-images/vocabularies")
async def get_reference_vocabularies():
    """获取参考图分类受控词表（供前端下拉使用）"""
    from app.image_provider import ReferenceImageClassifier

    return ReferenceImageClassifier.get_vocabularies()


# ──────────────────────────────────────────────────────────────
# 5. 参考图分类
# ──────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/reference-images/classify")
async def classify_reference_image(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    参考图分类接口
    v1：手动标签匹配受控词表 + DeepSeek 生成结构化说明（可选）
    """
    from app.image_provider import ReferenceImageClassifier
    from app.models import Project
    from app.services import call_deepseek_text

    body = await request.json()
    tags: list = body.get("tags", [])
    user_description: str = body.get("description", "")
    # image_path 可选，供将来视觉分类使用
    # image_path: str = body.get("image_path", "")

    project = db.query(Project).filter_by(id=project_id).first()
    if not project:
        return JSONResponse({"error": "项目不存在"}, status_code=404)

    classifier = ReferenceImageClassifier()

    # 手动分类（v1 默认）
    classification = classifier.classify_manual(tags, user_description)

    # DeepSeek 生成结构化说明（有用户描述时启用）
    ai_description = None
    if user_description:
        try:
            project_context = {
                "name": project.name,
                "project_type": getattr(project, "project_type", "") or "",
            }
            desc_prompt = classifier.build_description_prompt(
                project_context, user_description
            )
            system_prompt = (
                "你是建筑设计参考图分析师。请严格按照要求输出JSON格式内容，不要输出其他文字。"
            )
            ai_result = await call_deepseek_text(desc_prompt, system_prompt)
            if ai_result:
                ai_description = safe_json_parse(ai_result, default=None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI description generation failed: %s", exc)

    return {
        "classification": classification,
        "ai_description": ai_description,
        "vocabularies": classifier.get_vocabularies(),
    }


# ──────────────────────────────────────────────────────────────
# 6. 生成图片文件服务
# ──────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/image-file")
async def serve_generated_image(project_id: str, path: str = ""):
    """
    服务生成图片文件。
    path 参数是图片的本地绝对路径，经过安全校验后返回。
    """
    from app.security import PathValidationError, validate_path
    from app.config import settings

    if not path:
        return JSONResponse({"error": "缺少图片路径"}, status_code=400)

    # 路径安全校验
    allowed_bases = [settings.data_dir_path, settings.upload_root_path]
    if settings.image_output_dir:
        allowed_bases.append(Path(settings.image_output_dir))

    try:
        validated = validate_path(path, allowed_bases=allowed_bases, must_exist=True)
    except PathValidationError as exc:
        logger.warning("Image file path validation failed: %s", exc)
        return JSONResponse({"error": f"路径校验失败: {exc}"}, status_code=403)

    if not validated.is_file():
        return JSONResponse({"error": "图片文件不存在"}, status_code=404)

    return FileResponse(
        path=str(validated),
        media_type="image/png",
        filename=validated.name,
    )
