######## State Based Logic #######
# 1. Dead Time - ball is not active and server is not in ready position.
# 2. Armed (Serve Ready) - ball is not active, and server is in ready position for the required time and there has not been a serve within a timegate.
# - Use my current pipeline of detect_serves and serve_physics. (no Kalman filter necessary)
# 3. Serve Detected - ball toss detected and trophy position met.
# - This is more of an instantaneous state, but it marks the transition from serve to active play.
# 4. Active point play - ball is active.
# - In active play, track the ball with the combination of the Kalman filter and SAHI.  It is important to mask out static ball detections at the start.  Right now with 1 or 2 cameras
# , we are in this phase until ball velocity is below some threshold or ball has not been seen for XX amount of frames.  Once either of these conditions are met, we move to dead time or armed depending on ready position of server.
