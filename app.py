import streamlit as st
import pandas as pd
import numpy as np
import tempfile
import random
import copy
import base64
from music21 import converter, note, stream, midi

st.set_page_config(page_title="玄·律标注原型", layout="wide")
st.title("🎵 玄·律标注原型 (最终版·自动检测播放器)")
st.markdown("上传MIDI文件，生成变体，点击播放按钮试听。如果播放失败，请使用下载按钮。")

# 初始化session_state
if 'variants' not in st.session_state:
    st.session_state.variants = []
if 'variant_meta' not in st.session_state:
    st.session_state.variant_meta = []
if 'labels_surprise' not in st.session_state:
    st.session_state.labels_surprise = []
if 'labels_beauty' not in st.session_state:
    st.session_state.labels_beauty = []

# ---------- 生成变体函数 ----------
def generate_variant(melody_stream, surprise_strength=0.3):
    C_MAJOR = {0, 2, 4, 5, 7, 9, 11}
    COMMON_DURS = [0.5, 1, 2]
    original_notes = list(melody_stream.getElementsByClass(note.Note))
    if not original_notes:
        return stream.Stream()
    new_notes = [copy.deepcopy(n) for n in original_notes]
    n_changes = max(1, int(len(new_notes) * surprise_strength))
    for _ in range(n_changes):
        idx = random.randint(0, len(new_notes)-1)
        current = new_notes[idx]
        current_pitch = current.pitch.midi
        current_dur = current.quarterLength
        if random.random() < 0.7:
            attempts = 0
            new_pitch = None
            while attempts < 10:
                step = random.choice([-2, -1, 1, 2]) if surprise_strength > 0.5 else random.choice([-1, 1])
                candidate = current_pitch + step
                if (candidate % 12) in C_MAJOR and 0 <= candidate <= 127:
                    prev_pitch = new_notes[idx-1].pitch.midi if idx > 0 else candidate
                    next_pitch = new_notes[idx+1].pitch.midi if idx < len(new_notes)-1 else candidate
                    if abs(candidate - prev_pitch) <= 7 and abs(candidate - next_pitch) <= 7:
                        new_pitch = candidate
                        break
                attempts += 1
            if new_pitch is not None:
                current.pitch.midi = new_pitch
        else:
            if current_dur in COMMON_DURS:
                new_dur = random.choice([d for d in COMMON_DURS if d != current_dur])
                current.quarterLength = new_dur
        if surprise_strength > 0.8 and random.random() < 0.3:
            leap = random.choice([-7, 7])
            candidate = current_pitch + leap
            if (candidate % 12) in C_MAJOR and 0 <= candidate <= 127:
                current.pitch.midi = candidate
    new_stream = stream.Stream()
    for n in new_notes:
        new_stream.append(n)
    return new_stream
# ---------------------------------

def get_midi_bytes(melody_stream):
    temp = tempfile.NamedTemporaryFile(suffix='.mid', delete=False)
    mf = midi.translate.music21ObjectToMidiFile(melody_stream)
    mf.open(temp.name, 'wb')
    mf.write()
    mf.close()
    with open(temp.name, 'rb') as f:
        data = f.read()
    import os
    os.unlink(temp.name)
    return data

def midi_to_base64(midi_bytes):
    return base64.b64encode(midi_bytes).decode('utf-8')

def get_midi_player_html(midi_base64, player_id):
    """返回一个带有库加载检测的MIDI播放器HTML"""
    html = f"""
    <div style="border:1px solid #ddd; padding:8px; margin:5px 0; border-radius:5px; background:#f9f9f9;">
        <button onclick="play_{player_id}()">▶️ 播放</button>
        <button onclick="stop_{player_id}()">⏹️ 停止</button>
        <span id="status_{player_id}" style="margin-left:10px;">⚪ 准备就绪</span>
        <div id="debug_{player_id}" style="font-size:0.8em; color:#666; margin-top:4px;"></div>
    </div>
    <script>
    (function() {{
        // 尝试从多个CDN加载MidiPlayer库
        function loadScript(url, callback) {{
            var script = document.createElement('script');
            script.type = 'text/javascript';
            script.src = url;
            script.onload = callback;
            script.onerror = function() {{
                console.log('Failed to load ' + url);
                callback(new Error('加载失败'));
            }};
            document.head.appendChild(script);
        }}

        var player_{player_id};
        var isPlaying_{player_id} = false;
        var libLoaded = false;

        // 检查库是否已存在，否则加载
        function ensureLib(callback) {{
            if (window.MidiPlayer) {{
                libLoaded = true;
                callback();
                return;
            }}
            // 尝试两个CDN
            var cdnList = [
                'https://cdn.jsdelivr.net/npm/midijs@2.0.0/dist/MidiPlayer.min.js',
                'https://unpkg.com/midijs@2.0.0/dist/MidiPlayer.min.js'
            ];
            var attempt = 0;
            function tryNext() {{
                if (attempt >= cdnList.length) {{
                    document.getElementById('debug_{player_id}').innerText = '所有CDN均加载失败，请使用下载。';
                    callback(new Error('库加载失败'));
                    return;
                }}
                loadScript(cdnList[attempt], function(err) {{
                    if (!err && window.MidiPlayer) {{
                        libLoaded = true;
                        callback();
                    }} else {{
                        attempt++;
                        tryNext();
                    }}
                }});
            }}
            tryNext();
        }}

        window.play_{player_id} = function() {{
            if (isPlaying_{player_id}) {{
                document.getElementById('debug_{player_id}').innerText = '已经在播放中';
                return;
            }}
            ensureLib(function(err) {{
                if (err) {{
                    document.getElementById('status_{player_id}').innerText = '❌ 播放器不可用';
                    return;
                }}
                document.getElementById('status_{player_id}').innerText = '⏳ 解码中...';
                try {{
                    var binary = atob("{midi_base64}");
                    var array = new Uint8Array(binary.length);
                    for (var i = 0; i < binary.length; i++) {{
                        array[i] = binary.charCodeAt(i);
                    }}
                    var blob = new Blob([array], {{ type: 'audio/midi' }});
                    var url = URL.createObjectURL(blob);

                    player_{player_id} = new MidiPlayer.Player(function(event) {{
                        if (event.message === 0x3F) {{ // End of track
                            document.getElementById('status_{player_id}').innerText = '✅ 播放结束';
                            isPlaying_{player_id} = false;
                        }}
                    }});

                    player_{player_id}.loadFile(url, function() {{
                        document.getElementById('status_{player_id}').innerText = '▶️ 播放中...';
                        document.getElementById('debug_{player_id}').innerText = '';
                        isPlaying_{player_id} = true;
                        player_{player_id}.play();
                    }});
                }} catch (e) {{
                    document.getElementById('status_{player_id}').innerText = '❌ 播放失败';
                    document.getElementById('debug_{player_id}').innerText = '错误: ' + e.message;
                    console.error(e);
                }}
            }});
        }};

        window.stop_{player_id} = function() {{
            if (player_{player_id} && isPlaying_{player_id}) {{
                player_{player_id}.stop();
                document.getElementById('status_{player_id}').innerText = '⏹️ 已停止';
                isPlaying_{player_id} = false;
                document.getElementById('debug_{player_id}').innerText = '';
            }}
        }};
    }})();
    </script>
    """
    return html

# 侧边栏
with st.sidebar:
    st.header("1. 导入MIDI文件")
    uploaded_files = st.file_uploader("选择MIDI文件", type=['mid','midi'], accept_multiple_files=True)

    raw_melodies = []
    if uploaded_files:
        for f in uploaded_files:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mid') as tmp:
                tmp.write(f.read())
                tmp_path = tmp.name
            try:
                score = converter.parse(tmp_path)
                note_list = list(score.parts[0].flat.getElementsByClass(note.Note))
                if note_list:
                    melody_stream = stream.Stream(note_list)
                    raw_melodies.append(melody_stream)
                    st.success(f"已导入: {f.name}")
                else:
                    st.warning(f"无音符: {f.name}")
            except Exception as e:
                st.error(f"解析失败: {f.name} - {str(e)}")
            import os
            os.unlink(tmp_path)

    st.header("2. 生成变体")
    n_per_original = st.number_input("每首生成变体数", min_value=1, max_value=10, value=3)
    if st.button("生成变体"):
        if not raw_melodies:
            st.warning("请先导入MIDI")
        else:
            st.session_state.variants = []
            st.session_state.variant_meta = []
            for mel in raw_melodies:
                for i in range(n_per_original):
                    strength = random.uniform(0.2, 0.8)
                    var = generate_variant(mel, strength)
                    st.session_state.variants.append(var)
                    st.session_state.variant_meta.append({
                        'original_idx': len(raw_melodies)-1,
                        'surprise_strength': strength
                    })
            st.session_state.labels_surprise = [None] * len(st.session_state.variants)
            st.session_state.labels_beauty = [None] * len(st.session_state.variants)
            st.success(f"已生成 {len(st.session_state.variants)} 个变体")

# 主界面：标注（默认展开）
st.header("3. 标注变体")
if st.session_state.variants:
    for idx, var in enumerate(st.session_state.variants[:10]):  # 只显示前10个
        with st.expander(f"变体 #{idx}", expanded=True):
            col1, col2 = st.columns([1,2])
            with col1:
                midi_bytes = get_midi_bytes(var)
                midi_b64 = midi_to_base64(midi_bytes)
                # 嵌入播放器
                player_html = get_midi_player_html(midi_b64, idx)
                st.components.v1.html(player_html, height=140)
                # 下载按钮
                st.download_button(
                    "⬇️ 下载MIDI文件",
                    data=midi_bytes,
                    file_name=f"variant_{idx}.mid",
                    mime="audio/midi",
                    key=f"download_{idx}"
                )
            with col2:
                current_s = st.session_state.labels_surprise[idx] if st.session_state.labels_surprise[idx] is not None else 0.5
                current_b = st.session_state.labels_beauty[idx] if st.session_state.labels_beauty[idx] is not None else 0.5
                new_s = st.slider("意外度", 0.0, 1.0, current_s, key=f"s_{idx}")
                new_b = st.slider("好听度", 0.0, 1.0, current_b, key=f"b_{idx}")
                if st.button("保存标注", key=f"save_{idx}"):
                    st.session_state.labels_surprise[idx] = new_s
                    st.session_state.labels_beauty[idx] = new_b
                    st.success("已保存")
else:
    st.info("请在左侧上传MIDI文件并生成变体")
