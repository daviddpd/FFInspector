# FF Inspector 
## FFMpeg video file inspector and report.

Generally, will be given a target, either file or directory, scanning directories recessively looking for video files, typically mp4 and mkv, but search for any support video container format supported by ffmpeg. 

This will be to audit my movies and tv shows, to see if the quality, audio, and subtiles.  Also, access the NFO file with the same name, and parse the information. Note, the NFO might have fileinfo with video and audio, the source of truth of course is the video itself, so use that info.  And if something doesn't match flag NFO out of sync in the report, but for exact decimal give grace for rounding errors or truncation.

Create in python. Initially will be a command line tool, but internally make modular so the report then can be output to different formats at a later time. 

The command line report, use coloring and advance UTF output as needed. Via CLI and config file, use YAML for config, should be able to re-arrange the output, which should include 

    - meta
        title:
        mpaa/or TV rating (if contained in the NFO)
        season  (tv only)
        episode (tv only)
        aired/premiered date
    - video 
        - Duration, Format: 00:43:48, hh:mm ... round to nearest minute.
        - Codec: H.265, H,264, etc
        - Resolution :  4k, 1080p, 720p
        - exact resolution: 1920x1080
        - aspect ratio 
        - FPS
        - bitrate
        - Video Dynamic Range: SDR/HDR, etc and format, Dobly Vision, HDR10, etc
    - audio
        - which track is default
        - channel format, 2.0, 5.1, 7.1, etc.
        - codec
        - "branding", like Dolby Digital Plus, Dolby Atmos, DTS, etc.
        - sample rate 
        - language (if it can be determined)
    - Subtitles
        - which track is default
        - language (if it can be determined) 
        - extra information
        - format, there are several formats like srt 

My initially usage is for a foreign language tv series, and the versions I downloaded don't seem to all have english subtiles and an english audio dub. So, need a feature along the lines to "find missing english subtitles and audio" ... but make it generic enough, so it could be used for any language.  
