try:
    from utils.ActionHandler import ActionHandler
    from utils.common import CommonUtils
except ModuleNotFoundError:
    from .ActionHandler import ActionHandler
    from .common import CommonUtils

class CustomActionHandler(ActionHandler):
    """用户自定义的 ActionHandler"""
    
    def handle_text_to_speech(self, config, command, response, context):
        """
        文字转语音功能
        
        用法:
        {
            "text_to_speech": {
                "text": "Hello world",
                "voice": "female"
            }
        }
        """
        text = self.handle_variables_from_str(config.get("text", ""))
        voice = config.get("voice", "default")
        rate = config.get("rate")
        volume = config.get("volume")
        save_to = config.get("save_to")  # 可选：保存为音频文件，传入文件路径

        CommonUtils.print_log_line(f"🔊 播放语音({voice}): {text}")
        CommonUtils.print_log_line("")

        if not text:
            CommonUtils.print_log_line("❌ TTS: text 为空，跳过播放")
            return False

        try:
            import pyttsx3

            engine = pyttsx3.init()

            # 选择 voice（如果文本包含中文则优先选择支持中文的本地 voice；否则按配置选择）
            try:
                import re
                voices = engine.getProperty('voices') or []
                chosen_voice = None
                v_lower = str(voice).lower()

                # 检测文本是否包含中文
                try:
                    contains_chinese = bool(re.search(r"[\u4e00-\u9fff]", text))
                except Exception:
                    contains_chinese = False

                # 如果文本包含中文，先试着找到支持中文的 voice
                if contains_chinese:
                    for v in voices:
                        name = (getattr(v, 'name', '') or '').lower()
                        vid = (getattr(v, 'id', '') or '').lower()
                        langs = []
                        try:
                            langs = [l.decode('utf-8', errors='ignore').lower() if isinstance(l, (bytes, bytearray)) else str(l).lower() for l in (getattr(v, 'languages', []) or [])]
                        except Exception:
                            langs = []

                        name_id_text = name + ' ' + vid + ' ' + ' '.join(langs)
                        # 常见中文指示词
                        chinese_indicators = ['zh', 'zh-cn', 'zh_cn', 'chinese', '中文', 'yao', 'hui', 'xiaoyan', 'xiaoyao', 'xia', 'ya']
                        if any(ind in name_id_text for ind in chinese_indicators):
                            chosen_voice = v
                            break

                # 如果没有找到中文 voice 或文本不含中文，按用户配置选择
                if not chosen_voice:
                    if v_lower in ('female', 'woman'):
                        for v in voices:
                            if 'female' in (getattr(v,'name','') or '').lower() or 'female' in (getattr(v,'id','') or '').lower():
                                chosen_voice = v
                                break
                        if not chosen_voice and len(voices) > 1:
                            chosen_voice = voices[1]
                    elif v_lower in ('male', 'man'):
                        for v in voices:
                            if 'male' in (getattr(v,'name','') or '').lower() or 'male' in (getattr(v,'id','') or '').lower():
                                chosen_voice = v
                                break
                        if not chosen_voice and len(voices) > 0:
                            chosen_voice = voices[0]
                    else:
                        for v in voices:
                            if v_lower in (getattr(v,'name','') or '').lower() or v_lower in (getattr(v,'id','') or '').lower():
                                chosen_voice = v
                                break

                if chosen_voice:
                    engine.setProperty('voice', chosen_voice.id)
                else:
                    if contains_chinese:
                        CommonUtils.print_log_line("ℹ️ 未检测到支持中文的本地语音，若需播放中文请在系统设置中安装中文语音包，或使用在线 TTS。")
            except Exception:
                # 忽略 voice 选择错误，继续使用默认
                pass

            # 可选速率和音量
            try:
                if rate is not None:
                    engine.setProperty('rate', int(rate))
            except Exception:
                pass

            try:
                if volume is not None:
                    # pyttsx3 volume 范围 0.0 - 1.0
                    engine.setProperty('volume', float(volume))
            except Exception:
                pass

            # 支持保存为音频文件
            if save_to:
                save_path = self.handle_variables_from_str(save_to)
                CommonUtils.print_log_line(f"💾 保存为音频文件: {save_path}")
                engine.save_to_file(text, save_path)
                engine.runAndWait()
                CommonUtils.print_log_line("✅ 保存音频完成")
                return True

            # 播放
            engine.say(text)
            engine.runAndWait()
            CommonUtils.print_log_line("✅ 语音播放完成")
            return True
        except Exception as e:
            CommonUtils.print_log_line(f"❌ TTS 失败: {e}")
            CommonUtils.print_log_line("ℹ️ 如果未安装依赖，请运行: pip install pyttsx3")
            return False
        
    def handle_speech_to_text(self, config, command, response, context):
        """
        从麦克风录音并识别（离线 VOSK）
        用法:
        {
        "speech_to_text": {
            "duration": 5,                  # 录音秒数，默认 5
            "model_path": "models/vosk-model-cn",  # VOSK 模型目录
            "save_to": {"device":"DeviceA","variable":"last_stt"}  # 可选，保存识别结果
        }
        }
        """
        duration = float(config.get("duration", 5))
        model_path = config.get("model_path", "models/vosk-model-cn")
        sample_rate = int(config.get("sample_rate", 16000))
        device = config.get("device", None)  # 可选麦克风设备索引或名称
        silence_timeout = float(config.get("silence_timeout", 0))  # 0 表示禁用静默提前结束
        save_file = config.get("save_file", None)  # 可选：把识别结果保存为文本文件

        try:
            try:
                from vosk import Model, KaldiRecognizer
            except Exception:
                CommonUtils.print_log_line("❌ 未安装 VOSK，请运行: pip install vosk")
                return False
            try:
                import sounddevice as sd
            except Exception:
                CommonUtils.print_log_line("❌ 未安装 sounddevice，请运行: pip install sounddevice（Windows 可能需要安装 PortAudio）")
                return False

            import queue, json, os, time

            if not os.path.exists(model_path):
                CommonUtils.print_log_line(f"❌ VOSK model not found at {model_path}")
                CommonUtils.print_log_line("ℹ️ 请从 https://alphacephei.com/vosk/models 下载中文模型并解压到该路径")
                return False

            # 如果指定了设备但无法识别，打印可用设备
            try:
                selected_device = None
                if device is not None:
                    try:
                        # device 可能是索引或名称
                        if isinstance(device, int) or str(device).isdigit():
                            selected_device = int(device)
                        else:
                            # 查找匹配名称
                            devs = sd.query_devices()
                            for idx, d in enumerate(devs):
                                if str(device).lower() in str(d.get('name','')).lower():
                                    selected_device = idx
                                    break
                    except Exception:
                        selected_device = None
                    if selected_device is None:
                        CommonUtils.print_log_line(f"⚠️ 未找到指定设备 '{device}'，将使用默认设备。可用设备列表:")
                        for i, d in enumerate(sd.query_devices()):
                            CommonUtils.print_log_line(f"  {i}: {d.get('name')}")

            except Exception:
                selected_device = None

            model = Model(model_path)
            rec = KaldiRecognizer(model, sample_rate)
            q = queue.Queue()

            def callback(indata, frames, time_info, status):
                if status:
                    pass
                q.put(bytes(indata))

            CommonUtils.print_log_line(f"🎤 开始录音 {duration} 秒 (sample_rate={sample_rate})...")
            parts = []
            last_voice_time = time.time()
            try:
                stream_kwargs = dict(samplerate=sample_rate, blocksize=8000, dtype='int16', channels=1, callback=callback)
                if device is not None and selected_device is not None:
                    stream_kwargs['device'] = selected_device

                with sd.RawInputStream(**stream_kwargs):
                    t_end = time.time() + duration
                    while time.time() < t_end:
                        try:
                            data = q.get(timeout=0.5)
                        except queue.Empty:
                            # 检查静默提前结束
                            if silence_timeout and (time.time() - last_voice_time) > silence_timeout:
                                CommonUtils.print_log_line("⏱️ 检测到静默，提前结束录音")
                                break
                            continue
                        if rec.AcceptWaveform(data):
                            res = json.loads(rec.Result())
                            text = res.get("text", "").strip()
                            if text:
                                parts.append(text)
                                last_voice_time = time.time()
                        else:
                            # 可以获取部分结果，但这里不追加
                            pass
                    # final
                    final = json.loads(rec.FinalResult())
                    if final.get("text"):
                        parts.append(final.get("text"))
            except KeyboardInterrupt:
                CommonUtils.print_log_line("ℹ️ 录音被中断")
            except Exception as e:
                CommonUtils.print_log_line(f"❌ 录音错误: {e}")
                return False

            result_text = " ".join(p for p in parts if p)
            CommonUtils.print_log_line(f"✅ 识别结果: {result_text}")

            # 保存到文本文件（可选）
            if save_file:
                try:
                    with open(self.handle_variables_from_str(save_file), 'w', encoding='utf-8') as f:
                        f.write(result_text)
                    CommonUtils.print_log_line(f"💾 识别文本已保存到: {save_file}")
                except Exception as e:
                    CommonUtils.print_log_line(f"⚠️ 无法保存识别文本到文件: {e}")

            # 保存到 data_store（项目内变量）
            if "save_to" in config:
                s = config["save_to"]
                try:
                    self.executor.data_store.store_data(
                        self.handle_variables_from_str(s.get("device")),
                        self.handle_variables_from_str(s.get("variable")),
                        result_text,
                    )
                except Exception as e:
                    CommonUtils.print_log_line(f"⚠️ 保存到 data_store 失败: {e}")

            return True
        except Exception as e:
            CommonUtils.print_log_line(f"❌ STT 失败: {e}")
            return False

    def handle_http_request(self, config, command, response, context):
        """
        发送 HTTP 请求
        
        用法:
        {
            "http_request": {
                "url": "http://stservice.quectel.com:8300/iFishin/fish.txt",
                "method": "GET",
                "headers": {"Content-Type": "application/json"},
                "body": {"key": "value"},
                "save_to": {"device": "DeviceA", "variable": "api_response"}
            }
        }
        """
        try:
            import importlib
            requests = importlib.import_module('requests')
        except Exception:
            CommonUtils.print_log_line("❌ handle_http_request: 未安装 requests 库，请运行: pip install requests")
            return False
        import json
        
        url = self.handle_variables_from_str(config["url"])
        method = config.get("method", "GET").upper()
        headers = config.get("headers", {})
        body = config.get("body", None)
        
        CommonUtils.print_log_line(f"🌐 发送 {method} 请求到 {url}")
        CommonUtils.print_log_line("")
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=body)
            else:
                CommonUtils.print_log_line(f"❌ 不支持的 HTTP 方法: {method}")
                return False
                
            # 保存响应
            if "save_to" in config:
                save_to = config["save_to"]
                self.executor.data_store.store_data(
                    self.handle_variables_from_str(save_to["device"]),
                    self.handle_variables_from_str(save_to["variable"]),
                    response.text
                )
                
            CommonUtils.print_log_line(f"✅ HTTP 请求成功 (状态码: {response.status_code})")
            return True
        except Exception as e:
            CommonUtils.print_log_line(f"❌ HTTP 请求失败: {e}")
            return False