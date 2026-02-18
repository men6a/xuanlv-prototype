# 主界面：标注
st.header("3. 标注变体")
if st.session_state.variants:
    for idx, var in enumerate(st.session_state.variants[:10]):  # 只显示前10个
        with st.expander(f"变体 #{idx}"):
            col1, col2 = st.columns([1,2])
            with col1:
                # 生成MIDI字节数据
                midi_bytes = get_midi_data(var)
                
                # 创建播放按钮和音频播放器
                if st.button(f"▶️ 播放变体 #{idx}", key=f"play_{idx}"):
                    st.audio(midi_bytes, format="audio/midi", autoplay=True)
                
                # 同时保留下载按钮作为备选
                st.download_button(
                    "⬇️ 下载MIDI文件", 
                    data=midi_bytes, 
                    file_name=f"variant_{idx}.mid", 
                    mime="audio/midi",
                    key=f"download_{idx}"
                )
                
                st.caption("注：如果听不到声音，请点击页面空白处后再试 [citation:2]")
            
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
