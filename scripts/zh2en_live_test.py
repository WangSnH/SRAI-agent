from paperscout.config.settings import load_settings
from paperscout.services.zh2en_orchestrator import run_zh2en_init, run_zh2en_turn


def main() -> int:
    settings = load_settings()
    print("=== zh2en live integration test ===")

    try:
        init_data = run_zh2en_init(
            settings,
            thread_name="联调测试会话",
            original_input="请把我的中文翻译成自然英文。",
        )
    except Exception as e:
        print("INIT_FAILED:", type(e).__name__, str(e))
        return 2

    init_meta = {
        "zh2en_init_reply": init_data.get("zh2en_init_reply", ""),
        "used_model": init_data.get("used_model", ""),
        "zh2en_translation_list": init_data.get("zh2en_translation_list", []),
        "zh2en_latest_translation": init_data.get("zh2en_latest_translation", ""),
        "original_input": "请把我的中文翻译成自然英文。",
    }

    history = []

    user_text_1 = "请把这句话翻译成英文：我们提出了一种轻量级方法来提升模型的泛化能力。"
    out1 = run_zh2en_turn(settings, history=history, user_text=user_text_1, init_meta=init_meta)
    ans1 = out1.get("final_answer", "")
    meta1 = out1.get("updated_init_meta", {})
    print("\n[T1] task_type =", out1.get("task_type"))
    print("[T1] answer_preview =", (ans1[:220] + "...") if len(ans1) > 220 else ans1)
    print("[T1] cache_size =", len(meta1.get("zh2en_translation_list", []) if isinstance(meta1, dict) else []))

    history.append({"role": "user", "content": user_text_1})
    history.append({"role": "assistant", "content": ans1})

    user_text_2 = "把刚才译文改得更学术一些，并且更简洁。"
    out2 = run_zh2en_turn(settings, history=history, user_text=user_text_2, init_meta=meta1)
    ans2 = out2.get("final_answer", "")
    meta2 = out2.get("updated_init_meta", {})
    cache2 = meta2.get("zh2en_translation_list", []) if isinstance(meta2, dict) else []
    print("\n[T2] task_type =", out2.get("task_type"))
    print("[T2] answer_preview =", (ans2[:220] + "...") if len(ans2) > 220 else ans2)
    print("[T2] cache_size =", len(cache2))
    print("[T2] latest_translation_preview =", ((str(cache2[-1])[:220] + "...") if cache2 else ""))

    print("\nLIVE_TEST_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
