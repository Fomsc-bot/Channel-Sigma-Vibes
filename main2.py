# ================= VIDEO CREATION =================

def create_video(row):
    try:
        # --- Thumbnail selection ---
        thumb_file = None
        thumbnails = list(THUMB_DIR.glob("*"))
        if thumbnails:
            thumb_texts = [extract_text_from_image(f) for f in thumbnails]
            best_match, score = process.extractOne(row['Title'], thumb_texts)
            if score >= 80:
                idx = thumb_texts.index(best_match)
                thumb_file = thumbnails[idx]
        if not thumb_file:
            print(f"⚠ No thumbnail found for {row['Title']}, using random")
            thumbnails = list(THUMB_DIR.glob("*"))
            if thumbnails:
                thumb_file = random.choice(thumbnails)
            else:
                print("❌ No thumbnails available")
                return None

        bg_files = list(BG_DIR.glob("*"))
        outtro_files = list(OUTTRO_DIR.glob("*"))
        
        if not bg_files:
            print("❌ No background images available")
            return None
        
        bg_file = random.choice(bg_files)
        outtro_file = random.choice(outtro_files) if outtro_files else bg_file

        # --- Split sentences and generate TTS ---
        full_text = row['Voiceover Text']
        sentences = [s.strip() for s in full_text.replace("?", ".").replace("!", ".").split(".") if s.strip()]
        
        if not sentences:
            print("❌ No sentences found in voiceover text")
            return None
            
        tts_files = []
        sentence_durations = []
        for i, s in enumerate(sentences):
            tts_path = OUTPUT_DIR / f"{uuid.uuid4().hex}_tts_{i}.mp3"
            try:
                generate_voice(s, tts_path)
                # get duration
                success, output = run_ffmpeg_command([
                    "ffprobe", "-v", "error", "-show_entries",
                    "format=duration", "-of",
                    "default=noprint_wrappers=1:nokey=1", str(tts_path)
                ], "Failed to get audio duration")
                
                if success:
                    dur = float(output.strip())
                else:
                    dur = max(len(s.split()) / 2.5, 1)  # Fallback duration
            except Exception as e:
                print(f"⚠ TTS generation error: {e}")
                dur = max(len(s.split()) / 2.5, 1)
                # Create a dummy audio file if needed
                if not tts_path.exists():
                    # Create silent audio as fallback
                    run_ffmpeg_command([
                        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                        "-t", str(dur), str(tts_path)
                    ], "Failed to create fallback audio")
            
            tts_files.append(tts_path)
            sentence_durations.append(dur)

        # --- Merge TTS audio for final video ---
        merged_audio = OUTPUT_DIR / f"{uuid.uuid4().hex}_merged.mp3"
        tts_list_file = OUTPUT_DIR / "tts_list.txt"
        
        # Create concat file
        with open(tts_list_file, "w") as f:
            for t in tts_files:
                if t.exists():
                    f.write(f"file '{t.resolve()}'\n")
        
        # Merge audio files
        success, _ = run_ffmpeg_command([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(tts_list_file),
            "-c", "copy", str(merged_audio)
        ], "Failed to merge audio files")
        
        if not success or not merged_audio.exists():
            print("⚠ Audio merging failed, creating silent audio")
            total_duration = sum(sentence_durations)
            run_ffmpeg_command([
                "ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
                "-t", str(total_duration), str(merged_audio)
            ], "Failed to create silent audio")

        total_duration = sum(sentence_durations)
        total_frames = int(total_duration * FPS)
        writer_path = OUTPUT_DIR / f"{uuid.uuid4().hex}_temp.mp4"
        
        # Create video writer
        writer = cv2.VideoWriter(
            str(writer_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            FPS,
            (VIDEO_WIDTH, VIDEO_HEIGHT)
        )
        
        if not writer.isOpened():
            print("❌ Failed to open video writer")
            return None

        # --- Thumbnail with animation ---
        thumb_img = resize(Image.open(thumb_file))
        for i in range(THUMB_DURATION * FPS):
            # Fade in effect - REMOVED CAPTION FROM THUMBNAIL
            alpha = min(1.0, i / (FPS * 0.5))  # Fade in over 0.5 seconds
            frame_img = thumb_img.copy()
            # DON'T draw caption on thumbnail - just show the image
            # frame = draw_caption(frame_img, row['Title'], alpha=alpha)
            writer.write(cv2.cvtColor(np.array(frame_img), cv2.COLOR_RGB2BGR))

        # --- Main Scene ---
        bg_img = resize(Image.open(bg_file))
        zoom_end, pan_x, pan_y = prepare_ken_burns(bg_img)

        # Track sentence timing - START FROM BEGINNING AFTER THUMBNAIL
        frame_cursor = 0
        for s, dur in zip(sentences, sentence_durations):
            frames = int(dur * FPS)
            # Calculate animation frames for this sentence
            fade_frames = int(min(frames * 0.2, FPS * ANIMATION_DURATION))
            
            for i in range(frames):
                frame = ken_burns_frame(bg_img, frame_cursor + i, total_frames, zoom_end, pan_x, pan_y)
                
                # Calculate animation progress (fade in at start, fade out at end)
                animation_progress = 1.0
                if i < fade_frames:
                    # Fade in
                    animation_progress = i / fade_frames
                elif i > frames - fade_frames:
                    # Fade out
                    animation_progress = (frames - i) / fade_frames
                
                # Draw caption with animation
                frame = draw_caption(frame, s, animation_progress=animation_progress)
                writer.write(cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR))
            frame_cursor += frames

        # --- Outro ---
        outtro_img = resize(Image.open(outtro_file))
        outro_frames = OUTTRO_DURATION * FPS
        zoom_end_out, pan_x_out, pan_y_out = prepare_ken_burns(outtro_img)
        for i in range(outro_frames):
            # Fade out effect for outro
            alpha = max(0.0, 1.0 - (i / (outro_frames * 0.5)))
            frame = ken_burns_frame(outtro_img, i, outro_frames, zoom_end_out, pan_x_out, pan_y_out)
            # Add call to action text
            cta_text = "Like & Subscribe!"
            if i > outro_frames * 0.3:  # Show CTA after 30% of outro
                frame = draw_caption(frame, cta_text, alpha=alpha)
            writer.write(cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR))

        writer.release()

        # --- Create silent audio for thumbnail duration ---
        # Add silent audio at the beginning to sync voiceover with main content
        thumbnail_silence = OUTPUT_DIR / f"{uuid.uuid4().hex}_thumbnail_silence.mp3"
        run_ffmpeg_command([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", str(THUMB_DURATION), str(thumbnail_silence)
        ], "Failed to create thumbnail silence")
        
        # Merge thumbnail silence with voiceover audio
        final_audio = OUTPUT_DIR / f"{uuid.uuid4().hex}_final_audio.mp3"
        with open(OUTPUT_DIR / "audio_list.txt", "w") as f:
            f.write(f"file '{thumbnail_silence.resolve()}'\n")
            f.write(f"file '{merged_audio.resolve()}'\n")
        
        run_ffmpeg_command([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(OUTPUT_DIR / "audio_list.txt"),
            "-c", "copy", str(final_audio)
        ], "Failed to merge thumbnail silence with voiceover")
        
        # --- Merge video with final audio ---
        final_path = OUTPUT_DIR / f"{uuid.uuid4().hex}_final.mp4"
        
        # Use final_audio instead of merged_audio
        success, _ = run_ffmpeg_command([
            "ffmpeg", "-y",
            "-i", str(writer_path),
            "-i", str(final_audio),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            str(final_path)
        ], "Failed to merge video and audio")
        
        if not success:
            # Try simpler approach
            print("⚠ Trying alternative merge method...")
            success, _ = run_ffmpeg_command([
                "ffmpeg", "-y",
                "-i", str(writer_path),
                "-i", str(final_audio),
                "-c:v", "copy",
                "-c:a", "aac",
                str(final_path)
            ], "Alternative merge also failed")
        
        # --- Cleanup ---
        try:
            if writer_path.exists():
                writer_path.unlink()
            if merged_audio.exists():
                merged_audio.unlink()
            if final_audio.exists():
                final_audio.unlink()
            if thumbnail_silence.exists():
                thumbnail_silence.unlink()
            if tts_list_file.exists():
                tts_list_file.unlink()
            if (OUTPUT_DIR / "audio_list.txt").exists():
                (OUTPUT_DIR / "audio_list.txt").unlink()
            for t in tts_files:
                if t.exists():
                    t.unlink()
            # Don't delete thumb_file as it might be used by other videos
        except Exception as e:
            print(f"⚠ Cleanup error: {e}")

        if not success or not final_path.exists():
            print("❌ Video creation failed completely")
            return None

        print(f"✅ Video created successfully: {final_path}")
        return final_path
        
    except Exception as e:
        print(f"❌ Video creation failed: {e}")
        import traceback
        traceback.print_exc()
        return None
