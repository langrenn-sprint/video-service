# Google Live Stream API vs Traditional Python Capture

## Overview

This document compares two approaches to video capture for the video-service:

1. **Traditional Python Capture** (current): Using cv2.VideoCapture to capture from stream, store locally, then upload
2. **Google Live Stream API** (new): Using Google Cloud Live Stream API for cloud-native capture

## Architecture Comparison

### Traditional Python Capture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Video Stream│────▶│Python Service│────▶│Local Storage │────▶│Cloud Storage │
│  (SRT/HTTP) │     │(cv2.VideoCapt)│     │   (.mp4)     │     │  (GCS Bucket)│
└─────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │Frame Processing│
                    │  & Writing   │
                    └──────────────┘
```

**Characteristics:**
- Requires compute resources for frame capture and encoding
- Local disk space for temporary video storage
- Separate upload process to cloud storage
- Full control over video processing
- Can add watermarks, overlays, transformations

### Google Live Stream API

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────┐
│ Video Stream│────▶│Google Live Stream│────▶│Cloud Storage │
│  (SRT Push) │     │    API Service   │     │  (GCS Bucket)│
└─────────────┘     └──────────────────┘     └──────────────┘
                           │
                           ▼
                    ┌──────────────────┐
                    │   Automatic      │
                    │  Segmentation    │
                    └──────────────────┘
```

**Characteristics:**
- Cloud-native, fully managed service
- No local compute or storage required
- Direct streaming to cloud storage
- Automatic segmentation by duration
- Pay-per-use pricing model

## Feature Comparison

| Feature | Traditional Python | Live Stream API | Notes |
|---------|-------------------|-----------------|-------|
| **Infrastructure** | |||
| Compute Requirements | High (video processing) | None (serverless) | |
| Local Storage | Required | Not required | |
| Scalability | Manual (add servers) | Automatic | |
| **Video Capture** | |||
| Input Protocols | SRT, RTMP, HTTP | SRT Push, RTMP Push | |
| Output Format | MP4 | HLS (TS segments) | |
| Clip Duration | Configurable | Configurable | |
| Max Resolution | 4K (hardware dependent) | 1080p | API limitation |
| Frame Rate Control | Full control | Standard rates | |
| **Processing** | |||
| Real-time Processing | Yes (frame-by-frame) | No (post-capture) | |
| Watermarks/Overlays | Yes | No | |
| Custom Transformations | Yes | No | |
| **Storage** | |||
| Temporary Local Storage | Yes | No | |
| Direct Cloud Upload | After capture | During capture | |
| Storage Path Format | Custom | HLS manifest + segments | |
| **Reliability** | |||
| Fault Tolerance | Manual recovery | Built-in redundancy | |
| Stream Interruption Handling | Custom implementation | Automatic reconnection | |
| **Cost** | |||
| Compute Cost | High (24/7 if continuous) | Pay-per-use | |
| Storage Cost | Same (GCS) | Same (GCS) | |
| Data Transfer | Minimal (local → GCS) | May be higher | |
| API Usage Cost | None | Yes (Live Stream API) | |
| **Latency** | |||
| End-to-end Latency | 5-10 seconds | 10-30 seconds | HLS segmentation |
| Cloud Storage Availability | After full clip | Per segment | |
| **Development** | |||
| Setup Complexity | Medium | High (GCP setup) | |
| Code Maintenance | Custom code | API client | |
| Dependencies | OpenCV, cv2 | Google Cloud SDK | |

## Cost Analysis

### Traditional Python Capture

**Fixed Costs:**
- Compute instance (e.g., n1-standard-4): ~$140/month
- Local SSD storage (100GB): ~$17/month
- **Total Fixed: ~$157/month**

**Variable Costs:**
- GCS storage: $0.020 per GB/month
- Network egress: $0.12 per GB (first TB)

### Google Live Stream API

**Fixed Costs:**
- None (pay-per-use)

**Variable Costs:**
- Live Stream API: $3.00 per stream hour (HD 720p)
- GCS storage: $0.020 per GB/month
- Network ingress: Free
- Network egress: $0.12 per GB (first TB)

**Example Cost Calculation (24/7 streaming for 1 month):**
- Stream hours: 24 × 30 = 720 hours
- API cost: 720 × $3.00 = $2,160/month
- Storage: ~500GB × $0.020 = $10/month
- **Total: ~$2,170/month**

### Cost Comparison

| Scenario | Traditional | Live Stream API | Winner |
|----------|-------------|-----------------|--------|
| 24/7 continuous | $157 + storage | $2,170 + storage | Traditional |
| 8 hours/day | $157 + storage | $720 + storage | Traditional |
| 2 hours/day | $157 + storage | $180 + storage | API (marginal) |
| Event-based (10h/month) | $157 + storage | $30 + storage | API |

## When to Use Each Approach

### Use Traditional Python Capture When:

1. **Continuous streaming** (24/7 or many hours per day)
2. **Custom processing required** (watermarks, overlays, transformations)
3. **Frame-by-frame analysis** needed during capture
4. **Cost optimization** for high-volume scenarios
5. **Full control** over video encoding parameters
6. **Existing infrastructure** already in place

### Use Google Live Stream API When:

1. **Event-based streaming** (sporadic, short duration)
2. **No custom processing** required during capture
3. **Minimal infrastructure** preferred (serverless)
4. **Rapid deployment** needed
5. **Cloud-native architecture** desired
6. **Automatic failover** and reliability critical
7. **Low maintenance** overhead preferred

## Integration Scenarios

### Hybrid Approach

Both approaches can coexist in the same system:

```python
# Choose capture method based on event configuration
if event.get("use_live_stream_api"):
    # Use Google Live Stream API for this event
    from video_streaming.services import LiveStreamService
    service = LiveStreamService()
    await service.create_and_start_channel(event_id, clip_duration)
else:
    # Use traditional Python capture
    from video_service.services import VideoService
    service = VideoService()
    await service.capture_video(token, event, status_type, instance_name)
```

### Migration Path

1. **Phase 1**: Deploy Live Stream API solution alongside existing system
2. **Phase 2**: Test with selected events
3. **Phase 3**: Gradual migration based on event characteristics
4. **Phase 4**: Keep both systems for different use cases

## Technical Requirements

### Traditional Python Capture
- Python 3.13+
- OpenCV (opencv-python)
- Sufficient compute resources
- Local disk space

### Google Live Stream API
- Python 3.13+
- Google Cloud SDK
- google-cloud-video-live-stream library
- GCP project with Live Stream API enabled
- Service account with appropriate permissions

## Conclusion

The choice between traditional Python capture and Google Live Stream API depends on your specific use case:

- **High-volume, continuous streaming**: Traditional approach is more cost-effective
- **Event-based, sporadic streaming**: Live Stream API offers better ROI
- **Custom processing needs**: Traditional approach provides more flexibility
- **Minimal maintenance**: Live Stream API reduces operational overhead

The video-streaming module provides a ready-to-use implementation of the Live Stream API approach, allowing you to evaluate it alongside the existing solution and choose the best fit for each event or use case.
