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

**Cost per Hour:**
- For dedicated compute: Fixed cost amortized over usage
- Example: $157/month ÷ 730 hours/month = **$0.22/hour** (if running 24/7)
- For event-based usage: Fixed cost remains constant regardless of hours used

### Google Live Stream API

**Fixed Costs:**
- None (pay-per-use)

**Variable Costs:**
- Live Stream API: **$3.00 per stream hour** (HD 720p)
- GCS storage: $0.020 per GB/month
- Network ingress: Free
- Network egress: $0.12 per GB (first TB)

**Cost per Hour:**
- **$3.00/hour** for streaming
- Storage cost: ~$0.20/hour (assuming ~10GB/hour × $0.020/GB/month ÷ 30 days)
- **Total: ~$3.20/hour** (including storage)

### Cost Comparison by Scenario

| Scenario | Traditional | Live Stream API | Winner | Notes |
|----------|-------------|-----------------|--------|-------|
| **10-hour event** | **$157** (fixed) | **$30** | **Live Stream API** | Typical event duration |
| Single 10-hour event | $157 + $2 storage | $30 + $2 storage | **API ($32 vs $159)** | One event per month |
| 5 events × 10h (50h/month) | $157 + $10 storage | $150 + $10 storage | **API ($160 vs $167)** | Multiple events |
| 10 events × 10h (100h/month) | $157 + $20 storage | $300 + $20 storage | **Traditional ($177 vs $320)** | High frequency |
| 24/7 continuous (730h) | $157 + $150 storage | $2,190 + $150 storage | **Traditional ($307 vs $2,340)** | Always-on monitoring |

### Cost Per Hour Analysis

**Break-even Point:**
- Traditional: $157 fixed cost = 52 hours of Live Stream API ($3/hour)
- Below 52 hours/month → Live Stream API is cheaper
- Above 52 hours/month → Traditional is cheaper

**For 10-Hour Events:**
- **1 event/month**: Live Stream API saves $127 (81% savings)
- **5 events/month** (50 hours): Live Stream API saves $7 (4% savings)
- **6+ events/month**: Traditional becomes more cost-effective

**Cost Summary:**
```
Traditional Python Capture:
├─ Fixed: $157/month (regardless of usage)
├─ Effective cost/hour: $157 ÷ hours_used
└─ Best for: >52 hours/month or continuous operation

Live Stream API:
├─ Fixed: $0/month
├─ Cost/hour: $3.00 (consistent rate)
└─ Best for: <52 hours/month or sporadic events
```

## When to Use Each Approach

### Use Traditional Python Capture When:

1. **High-frequency events** (>52 hours/month or 6+ events of 10 hours)
2. **Continuous streaming** (24/7 or many hours per day)
3. **Custom processing required** (watermarks, overlays, transformations)
4. **Frame-by-frame analysis** needed during capture
5. **Full control** over video encoding parameters
6. **Existing infrastructure** already in place

### Use Google Live Stream API When:

1. **Typical event-based streaming** (1-5 events of ~10 hours per month)
2. **Sporadic or infrequent events** (<52 hours/month total)
3. **No custom processing** required during capture
4. **Minimal infrastructure** preferred (serverless)
5. **Rapid deployment** needed
6. **Cloud-native architecture** desired
7. **Automatic failover** and reliability critical
8. **Low maintenance** overhead preferred

**For 10-Hour Events:**
- 1-5 events/month → **Use Live Stream API** (significant cost savings)
- 6+ events/month → **Use Traditional** (fixed cost becomes more economical)

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

### Cost-Based Decision (for 10-hour events):
- **1-5 events/month** (10-50 hours): Live Stream API saves $7-127/month (4-81% savings)
- **6+ events/month** (60+ hours): Traditional approach becomes more cost-effective
- **Break-even point**: 52 hours/month (~5 events of 10 hours)

### Feature-Based Decision:
- **Custom processing needs**: Traditional approach provides more flexibility
- **Minimal infrastructure/maintenance**: Live Stream API reduces operational overhead
- **High-volume, continuous streaming**: Traditional approach is more cost-effective
- **Event-based, sporadic streaming**: Live Stream API offers better ROI

### Recommendation for Typical 10-Hour Events:
If you run **1-5 events per month**, the **Live Stream API is recommended** due to:
- Lower total cost ($30-160 vs $157-167)
- No infrastructure maintenance
- Pay only for actual usage
- Automatic scaling and reliability

If you run **6 or more events per month**, consider the **Traditional approach** as the fixed costs become more economical at higher usage levels.

The video-streaming module provides a ready-to-use implementation of the Live Stream API approach, allowing you to evaluate it alongside the existing solution and choose the best fit for each event or use case.
