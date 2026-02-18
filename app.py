import streamlit as st
import pandas as pd
import numpy as np
import tempfile
import random
import copy
import base64
import re
from music21 import converter, note, stream, midi, chord, interval, pitch, meter, instrument

st.set_page_config(page_title="玄·律标注原型", layout="wide")

# 隐藏页面加载遮罩
st.markdown("""
<style>
.stApp::before {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)

# 全局字体调小
st.markdown("""
<style>
html, body, [class*="css"]  {
    font-size: 0.9rem;
}
.main-title {
    font-size: 1.4rem;
    font-weight: bold;
    margin-bottom: 1rem;
}
.stSlider label {
    font-size: 0.9rem !important;
}
/* 侧边栏标题字体更小 */
.sidebar .sidebar-content h3 {
    font-size: 0.75rem !important;
    font-weight: 600;
}
/* 按钮极限贴近感受输入框 */
.button-row {
    margin-top: -18px !important;
}
.button-row .stButton button, .button-row .stDownloadButton button {
    font-size: 0.8rem !important;
    padding: 0.15rem 0.4rem !important;
    line-height: 1.2;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">🎵 玄·律标注原型</div>', unsafe_allow_html=True)
st.markdown("上传MIDI文件，从动机发展出带左手柱式和弦的完整乐段，并标注听感。")

# 初始化session_state
if 'variants' not in st.session_state:
    st.session_state.variants = []
if 'variant_meta' not in st.session_state:
    st.session_state.variant_meta = []
if 'labels_surprise' not in st.session_state:
    st.session_state.labels_surprise = []
if 'labels_beauty' not in st.session_state:
    st.session_state.labels_beauty = []
if 'labels_feelings' not in st.session_state:
    st.session_state.labels_feelings = []
if 'save_indicator' not in st.session_state:
    st.session_state.save_indicator = []

# ==================== 全维度音乐理论规则库 ====================

class MusicTheoryEngine:
    """音乐理论引擎：整合最新研究成果"""
    
    # 1. 调式音阶定义 
    SCALES = {
        'major': [0, 2, 4, 5, 7, 9, 11],     # 大调音阶
        'minor': [0, 2, 3, 5, 7, 8, 10],     # 自然小调
        'harmonic_minor': [0, 2, 3, 5, 7, 8, 11],  # 和声小调
        'melodic_minor': [0, 2, 3, 5, 7, 9, 11],   # 旋律小调上行
        'dorian': [0, 2, 3, 5, 7, 9, 10],    # 多利亚调式
        'mixolydian': [0, 2, 4, 5, 7, 9, 10], # 混合利底亚
    }
    
    # 2. 声部进行规则
    VOICE_LEADING = {
        'max_interval': 12,
        'prefer_step': 0.6,
        'prefer_skip': 0.3,
        'prefer_leap': 0.1,
        'contrary_motion': 0.4,
    }
    
    # 3. 风格一致性参数
    STYLE_CONSISTENCY = {
        'classical': {
            'ornament_prob': 0.3,
            'sequence_prob': 0.4,
            'repeat_prob': 0.3,
            'dissonance_tolerance': 0.2
        },
        'jazz': {
            'ornament_prob': 0.5,
            'sequence_prob': 0.2,
            'repeat_prob': 0.2,
            'dissonance_tolerance': 0.6
        },
        'folk': {
            'ornament_prob': 0.2,
            'sequence_prob': 0.3,
            'repeat_prob': 0.4,
            'dissonance_tolerance': 0.1
        }
    }
    
    # 4. 音程协和度矩阵
    CONSONANCE_MATRIX = {
        0: 1.0, 12: 1.0,
        7: 0.9, 19: 0.9,
        5: 0.8, 17: 0.8,
        4: 0.8, 3: 0.75, 16: 0.8, 15: 0.75,
        9: 0.7, 8: 0.65, 21: 0.7, 20: 0.65,
        2: 0.4, 10: 0.4, 14: 0.4, 22: 0.4,
        1: 0.1, 11: 0.1, 13: 0.1, 23: 0.1,
        6: 0.0, 18: 0.0
    }
    
    @classmethod
    def get_scale_notes(cls, key, mode):
        """获取指定调性的音阶音符（MIDI模12）"""
        note_to_idx = {'C':0, 'C#':1, 'Db':1, 'D':2, 'D#':3, 'Eb':3, 'E':4, 
                      'F':5, 'F#':6, 'Gb':6, 'G':7, 'G#':8, 'Ab':8, 'A':9, 
                      'A#':10, 'Bb':10, 'B':11}
        root = note_to_idx.get(key, 0)
        scale_pattern = cls.SCALES.get(mode, cls.SCALES['major'])
        return {(root + interval) % 12 for interval in scale_pattern}
    
    @classmethod
    def roman_or_num_to_degree(cls, token):
        """将罗马数字或阿拉伯数字转换为度数（0=I）"""
        token = token.strip()
        # 尝试阿拉伯数字
        if token.isdigit():
            num = int(token)
            if 1 <= num <= 7:
                return num - 1  # 1->0, 2->1, ...
        # 尝试罗马数字
        roman_map = {
            'I': 0, 'II': 1, 'III': 2, 'IV': 3, 'V': 4, 'VI': 5, 'VII': 6,
            'i': 0, 'ii': 1, 'iii': 2, 'iv': 3, 'v': 4, 'vi': 5, 'vii': 6
        }
        base = re.match(r'^[IiVv]+', token)
        if base:
            return roman_map.get(base.group(), 0)
        return 0  # 默认I
    
    @classmethod
    def get_chord_tones(cls, chord_degree, key='C', mode='major'):
        """
        根据度数获取和弦内音（MIDI模12）
        度数: 0=I, 1=II, ...
        简单实现：大三和弦（根音、根音+4、根音+7）
        """
        note_to_idx = {'C':0, 'C#':1, 'Db':1, 'D':2, 'D#':3, 'Eb':3, 'E':4, 
                      'F':5, 'F#':6, 'Gb':6, 'G':7, 'G#':8, 'Ab':8, 'A':9, 
                      'A#':10, 'Bb':10, 'B':11}
        root_idx = note_to_idx.get(key, 0)
        degree_to_interval = [0, 2, 4, 5, 7, 9, 11]  # 大调
        if chord_degree >= len(degree_to_interval):
            chord_degree = chord_degree % 7
        root_pitch_class = (root_idx + degree_to_interval[chord_degree]) % 12
        return {(root_pitch_class + offset) % 12 for offset in [0, 4, 7]}
    
    @classmethod
    def get_bass_note(cls, chord_degree, key='C', mode='major', octave=3):
        """获取指定和弦的根音音高（MIDI值），octave为八度（C4=60）"""
        note_to_idx = {'C':0, 'C#':1, 'Db':1, 'D':2, 'D#':3, 'Eb':3, 'E':4, 
                      'F':5, 'F#':6, 'Gb':6, 'G':7, 'G#':8, 'Ab':8, 'A':9, 
                      'A#':10, 'Bb':10, 'B':11}
        root_idx = note_to_idx.get(key, 0)
        degree_to_interval = [0, 2, 4, 5, 7, 9, 11]
        if chord_degree >= len(degree_to_interval):
            chord_degree = chord_degree % 7
        pitch_class = (root_idx + degree_to_interval[chord_degree]) % 12
        # 转换为MIDI音高：octave*12 + pitch_class，octave 0为C0
        return octave * 12 + pitch_class
    
    @classmethod
    def interval_consonance(cls, interval):
        interval = abs(interval) % 12
        return cls.CONSONANCE_MATRIX.get(interval, 0.5)

# ==================== 动机发展功能（带左右手） ====================

def get_total_measures(stream_obj):
    """获取流的总小节数（基于音符的measureNumber）"""
    measures = set()
    for n in stream_obj.flat.notes:
        if n.measureNumber is not None:
            measures.add(n.measureNumber)
    if measures:
        return max(measures)
    return 0

def extract_motif(original_stream, start_measure, length_measures):
    """
    从原始流中提取指定起始小节和长度的小节作为动机
    返回一个新的stream，包含这些小节的所有音符（保持原始offset）
    """
    motif_stream = stream.Stream()
    notes = list(original_stream.flat.notes)
    motif_notes = []
    for n in notes:
        if n.measureNumber is not None and start_measure <= n.measureNumber < start_measure + length_measures:
            motif_notes.append(n)
    
    if not motif_notes:
        return None
    
    motif_notes.sort(key=lambda x: x.offset)
    min_offset = motif_notes[0].offset
    for n in motif_notes:
        new_n = copy.deepcopy(n)
        new_n.offset = n.offset - min_offset
        motif_stream.append(new_n)
    
    return motif_stream

def apply_development(motif_notes, technique, scale_notes):
    """对音符列表应用发展手法"""
    if technique == "重复":
        return motif_notes
    elif technique == "倒影":
        if not motif_notes:
            return motif_notes
        axis = motif_notes[0].pitch.midi
        new_notes = []
        for n in motif_notes:
            new_n = copy.deepcopy(n)
            new_pitch = axis - (n.pitch.midi - axis)
            if (new_pitch % 12) not in scale_notes:
                best = new_pitch
                min_dist = 12
                for scale_note in scale_notes:
                    for octave in [-1, 0, 1]:
                        test = scale_note + ((new_pitch // 12) + octave) * 12
                        dist = abs(test - new_pitch)
                        if dist < min_dist and 0 <= test <= 127:
                            min_dist = dist
                            best = test
                new_pitch = best
            new_n.pitch.midi = new_pitch
            new_notes.append(new_n)
        return new_notes
    elif technique == "逆行":
        return list(reversed(motif_notes))
    else:
        return motif_notes

def limit_range(notes, min_pitch, max_pitch):
    """将音符限制在指定音域内，超出时八度移位"""
    for n in notes:
        p = n.pitch.midi
        if p < min_pitch:
            # 向上移八度直到进入范围
            while p < min_pitch:
                p += 12
        elif p > max_pitch:
            while p > max_pitch:
                p -= 12
        n.pitch.midi = p
    return notes

def develop_motif_with_progression_advanced(
    motif_stream, target_measures, chord_sequence_str,
    chords_per_bar, development_technique, stretch_factor,
    key='C', mode='major', beats_per_measure=4.0
):
    """
    将动机发展为指定小节数的乐段，支持自定义和弦进程、每小节和弦数、发展手法、节奏伸缩
    返回一个Score，包含右手旋律Part和左手柱式和弦Part
    """
    if motif_stream is None or len(motif_stream.notes) == 0:
        return stream.Score()
    
    # 解析和弦序列
    tokens = [s.strip() for s in re.split(r'[,\s]+', chord_sequence_str) if s.strip()]
    if not tokens:
        return stream.Score()
    
    chord_degrees = [MusicTheoryEngine.roman_or_num_to_degree(tok) for tok in tokens]
    
    chord_duration_beats = beats_per_measure / chords_per_bar
    total_chords_needed = int(target_measures * chords_per_bar)
    
    chord_cycle = []
    for i in range(total_chords_needed):
        chord_cycle.append(chord_degrees[i % len(chord_degrees)])
    
    # 处理右手旋律
    motif_notes = list(motif_stream.notes)
    scale_notes = MusicTheoryEngine.get_scale_notes(key, mode)
    developed_notes = apply_development(motif_notes, development_technique, scale_notes)
    
    if stretch_factor != 1.0:
        stretched_notes = []
        for n in developed_notes:
            new_n = copy.deepcopy(n)
            new_n.quarterLength = n.quarterLength * stretch_factor
            stretched_notes.append(new_n)
        developed_notes = stretched_notes
    
    # 计算原始动机的音域，用于限制右手旋律在2个八度内
    if developed_notes:
        pitches = [n.pitch.midi for n in developed_notes]
        avg_pitch = np.mean(pitches)
        # 设置音域范围：以平均音高为中心，上下12半音（两个八度）
        min_allowed = avg_pitch - 12
        max_allowed = avg_pitch + 12
        developed_notes = limit_range(developed_notes, min_allowed, max_allowed)
    
    # 创建右手Part
    right_part = stream.Part()
    right_part.partName = "右手旋律"
    right_part.id = 'right'
    right_part.append(instrument.Piano())
    
    # 左手Part
    left_part = stream.Part()
    left_part.partName = "左手和弦"
    left_part.id = 'left'
    left_part.append(instrument.Piano())
    
    # 生成乐段
    current_time = 0.0
    chord_index = 0
    while chord_index < len(chord_cycle):
        current_chord_degree = chord_cycle[chord_index]
        chord_tones = MusicTheoryEngine.get_chord_tones(current_chord_degree, key, mode)
        
        # 左手柱式和弦（根音、三音、五音）
        # 根音放在C3附近（octave=3），三音和五音根据和弦类型（大三和弦）确定
        root = MusicTheoryEngine.get_bass_note(current_chord_degree, key, mode, octave=3)
        # 三音：根音+4半音，但需要确保三音在调内（实际就是和弦内音）
        third = root + 4  # 大三度
        fifth = root + 7  # 纯五度
        # 确保音高在合理范围内
        chord_notes = [root, third, fifth]
        left_chord = chord.Chord(chord_notes)
        left_chord.quarterLength = chord_duration_beats
        left_chord.offset = current_time
        # 左手力度减小16%（相对于标准力度100）
        left_chord.volume.velocity = 84
        left_part.append(left_chord)
        
        # 右手旋律：将动机中的音符逐个添加，并调整音高到当前和弦内音
        for n in developed_notes:
            new_n = copy.deepcopy(n)
            new_n.offset = current_time + n.offset
            
            orig_pitch = n.pitch.midi
            if (orig_pitch % 12) not in chord_tones:
                # 调整到最近的和弦内音
                best_pitch = orig_pitch
                min_dist = 12
                for ct in chord_tones:
                    for octave in [-1, 0, 1]:
                        test_pitch = ct + ((orig_pitch // 12) + octave) * 12
                        dist = abs(test_pitch - orig_pitch)
                        if dist < min_dist and 0 <= test_pitch <= 127:
                            min_dist = dist
                            best_pitch = test_pitch
                new_n.pitch.midi = best_pitch
            
            right_part.append(new_n)
        
        current_time += chord_duration_beats
        chord_index += 1
    
    # 创建Score并添加两个Part
    score = stream.Score()
    score.append(right_part)
    score.append(left_part)
    
    return score

# ==================== 辅助函数 ====================

def get_midi_bytes(score):
    """将music21 Score转换为MIDI文件字节数据"""
    temp = tempfile.NamedTemporaryFile(suffix='.mid', delete=False)
    mf = midi.translate.music21ObjectToMidiFile(score)
    mf.open(temp.name, 'wb')
    mf.write()
    mf.close()
    with open(temp.name, 'rb') as f:
        data = f.read()
    import os
    os.unlink(temp.name)
    return data

def get_midi_player_html(midi_bytes, player_id):
    import base64
    midi_base64 = base64.b64encode(midi_bytes).decode('utf-8')
    data_url = f"data:audio/midi;base64,{midi_base64}"
    html = f"""
    <div style="margin:0; padding:0; background:transparent; line-height:0;">
        <script src="https://cdn.jsdelivr.net/combine/npm/tone@14.7.58,npm/@magenta/music@1.23.1/es6/core.js,npm/focus-visible@5,npm/html-midi-player@1.5.0"></script>
        <midi-player
            id="player-{player_id}"
            src="{data_url}"
            sound-font
            style="
                width:100%;
                margin:0;
                padding:0;
                display:block;
                background: transparent;
                border: none;
                box-shadow: none;
                outline: none;
                --midi-player-background: transparent;
                --midi-player-progress-background: transparent;
                --midi-player-button-color: #2d4a1e;
                --midi-player-progress-color: #2d4a1e;
                --midi-player-handle-color: #2d4a1e;
            ">
        </midi-player>
    </div>
    """
    return html

# ==================== 侧边栏UI ====================

with st.sidebar:
    st.markdown("### 1. 导入MIDI文件")
    uploaded_files = st.file_uploader("选择MIDI文件", type=['mid','midi'], accept_multiple_files=True)
    raw_melodies = []
    if uploaded_files:
        for f in uploaded_files:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mid') as tmp:
                tmp.write(f.read())
                tmp_path = tmp.name
            try:
                score = converter.parse(tmp_path)
                # 提取第一个Part作为旋律（假设是单旋律）
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

    st.markdown("### 2. 动机发展")
    if raw_melodies:
        total_measures = get_total_measures(raw_melodies[0])
        st.caption(f"当前MIDI总小节数: {total_measures}")
        
        key_options = ['C', 'G', 'D', 'A', 'E', 'F', 'Bb', 'Eb', 'Ab']
        selected_key = st.selectbox("调性", key_options, index=0)
        
        mode_options = ['major', 'minor', 'harmonic_minor', 'melodic_minor', 'dorian', 'mixolydian']
        selected_mode = st.selectbox("调式", mode_options, index=0)
        
        style_options = ['classical', 'jazz', 'folk']
        selected_style = st.selectbox("风格", style_options, index=0)
        
        start_measure = st.number_input("起始小节", min_value=1, max_value=max(1, total_measures), value=1)
        motif_length = st.number_input("动机长度（小节）", min_value=1, max_value=16, value=2)
        target_length = st.number_input("目标乐段长度（小节）", min_value=1, max_value=64, value=18)
        
        default_prog = "1,4,5,1"
        chord_prog_input = st.text_input("和弦进程（罗马数字或阿拉伯数字，逗号或空格分隔）", value=default_prog)
        
        chords_per_bar = st.selectbox("每小节和弦数", [1, 2, 3, 4], index=0)
        dev_technique = st.selectbox("发展手法", ["重复", "倒影", "逆行"], index=0)
        stretch_factor = st.slider("节奏伸缩因子", 0.5, 2.0, 1.0, step=0.1)
        
        if st.button("生成带伴奏的乐段"):
            if not raw_melodies:
                st.warning("请先导入MIDI")
            else:
                source_stream = raw_melodies[0]
                motif = extract_motif(source_stream, start_measure, motif_length)
                if motif is None or len(motif.notes) == 0:
                    st.error("指定小节内无音符，请调整范围")
                else:
                    developed_score = develop_motif_with_progression_advanced(
                        motif, target_length, chord_prog_input,
                        chords_per_bar, dev_technique, stretch_factor,
                        key=selected_key, mode=selected_mode, beats_per_measure=4.0
                    )
                    new_idx = len(st.session_state.variants)
                    st.session_state.variants.append(developed_score)
                    st.session_state.variant_meta.append({
                        'type': 'development_advanced',
                        'start_measure': start_measure,
                        'motif_length': motif_length,
                        'target_length': target_length,
                        'chord_prog': chord_prog_input,
                        'chords_per_bar': chords_per_bar,
                        'technique': dev_technique,
                        'stretch': stretch_factor,
                        'key': selected_key,
                        'mode': selected_mode,
                        'style': selected_style
                    })
                    st.session_state.labels_surprise.append(None)
                    st.session_state.labels_beauty.append(None)
                    st.session_state.labels_feelings.append("")
                    st.session_state.save_indicator.append("")
                    st.success(f"已生成带伴奏的乐段，作为变体 #{new_idx} 添加")
    else:
        st.info("请先导入MIDI文件")

# ==================== 主界面 ====================

if st.session_state.variants:
    for idx, var in enumerate(st.session_state.variants[:10]):
        indicator = st.session_state.save_indicator[idx] if idx < len(st.session_state.save_indicator) else ""
        meta = st.session_state.variant_meta[idx] if idx < len(st.session_state.variant_meta) else {}
        
        if meta:
            param_str = (f"动机发展: {meta.get('start_measure')}小节起{meta.get('motif_length')}小节 → {meta.get('target_length')}小节 | "
                         f"调性:{meta.get('key','C')} {meta.get('mode','major')} {meta.get('style','classical')} | "
                         f"和弦:{meta.get('chord_prog')} | 密度:{meta.get('chords_per_bar')}/小节 | "
                         f"手法:{meta.get('technique')} | 伸缩:{meta.get('stretch')}")
        else:
            param_str = "变体"
        
        expander_title = f"变体 #{idx} {indicator}  {param_str}"
        
        with st.expander(expander_title, expanded=True):
            left_col, right_col = st.columns(2)
            with left_col:
                midi_bytes = get_midi_bytes(var)
                player_html = get_midi_player_html(midi_bytes, idx)
                st.components.v1.html(player_html, height=60)

                if idx < len(st.session_state.labels_feelings):
                    current_f = st.session_state.labels_feelings[idx] if st.session_state.labels_feelings[idx] is not None else ""
                else:
                    current_f = ""
                st.text_area(
                    "感受词",
                    value=current_f,
                    height=80,
                    placeholder="请标注变体听感（例如：跳跃、不协和、温柔...）",
                    key=f"f_{idx}",
                    label_visibility="collapsed"
                )

                st.markdown('<div class="button-row">', unsafe_allow_html=True)
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    st.download_button(
                        "⬇️ 下载MIDI文件",
                        data=get_midi_bytes(var),
                        file_name=f"variant_{idx}.mid",
                        mime="audio/midi",
                        key=f"download_{idx}"
                    )
                with btn_col2:
                    if st.button("💾 保存标注", key=f"save_left_{idx}"):
                        current_s = st.session_state.get(f"s_{idx}", 0.5)
                        current_b = st.session_state.get(f"b_{idx}", 0.5)
                        current_f = st.session_state.get(f"f_{idx}", "")

                        while len(st.session_state.labels_surprise) <= idx:
                            st.session_state.labels_surprise.append(None)
                        while len(st.session_state.labels_beauty) <= idx:
                            st.session_state.labels_beauty.append(None)
                        while len(st.session_state.labels_feelings) <= idx:
                            st.session_state.labels_feelings.append("")
                        while len(st.session_state.save_indicator) <= idx:
                            st.session_state.save_indicator.append("")

                        st.session_state.labels_surprise[idx] = current_s
                        st.session_state.labels_beauty[idx] = current_b
                        st.session_state.labels_feelings[idx] = current_f
                        st.session_state.save_indicator[idx] = "✅"
                        st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

            with right_col:
                if idx < len(st.session_state.labels_surprise):
                    current_s = st.session_state.labels_surprise[idx] if st.session_state.labels_surprise[idx] is not None else 0.5
                else:
                    current_s = 0.5
                if idx < len(st.session_state.labels_beauty):
                    current_b = st.session_state.labels_beauty[idx] if st.session_state.labels_beauty[idx] is not None else 0.5
                else:
                    current_b = 0.5
                new_s = st.slider("意外度评分", 0.0, 1.0, current_s, key=f"s_{idx}")
                new_b = st.slider("好听度评分", 0.0, 1.0, current_b, key=f"b_{idx}")
else:
    st.info("请在左侧上传MIDI文件，并在动机发展中生成带伴奏的乐段")
