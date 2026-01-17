# Video Streaming with Google Live Stream API

This module provides an alternative solution for video capture using Google Live Stream API instead of the Python-based VideoService.capture_video().

## Overview

The current video-service captures video using Python libraries (cv2.VideoCapture), stores locally, and uploads to cloud buckets. This alternative solution uses Google Cloud Live Stream API to:
- Capture video streams directly from SRT Push sources
- Store video clips directly to cloud buckets
- Configure video clip duration dynamically

## Architecture

### Components

1. **LiveStreamService**: Main service class for managing live stream operations
2. **LiveStreamAdapter**: Adapter for Google Live Stream API interactions
3. **Configuration**: Settings for channels, inputs, outputs, and clip duration

### Google Live Stream API Resources

The solution uses the following Google Cloud resources:
- **Channel**: Manages the live stream processing
- **Input**: Defines the SRT Push endpoint for video ingestion
- **Output**: Configures cloud storage destination and segmentation

## Setup

### Prerequisites

1. Google Cloud Project with Live Stream API enabled
2. Service account with permissions:
   - `livestream.admin`
   - `storage.objectAdmin`
3. Cloud Storage bucket for video output

### Configuration

Create a configuration file or set environment variables:

```json
{
  "GOOGLE_CLOUD_PROJECT": "your-project-id",
  "GOOGLE_CLOUD_REGION": "us-central1",
  "GOOGLE_STORAGE_BUCKET": "your-bucket-name",
  "VIDEO_CLIP_DURATION": 30,
  "SRT_PORT": 5000
}
```

### Environment Variables

- `GOOGLE_CLOUD_PROJECT`: GCP project ID
- `GOOGLE_CLOUD_REGION`: Region for Live Stream API resources (default: us-central1)
- `GOOGLE_STORAGE_BUCKET`: Cloud storage bucket name
- `VIDEO_CLIP_DURATION`: Duration of each video clip in seconds (default: 30)
- `SRT_PORT`: Port for SRT Push input (default: 5000)

## Usage

### Starting a Live Stream

```python
from video_streaming.services.live_stream_service import LiveStreamService

service = LiveStreamService()

# Create and start a live stream channel
channel_info = await service.create_and_start_channel(
    event_id="event-123",
    clip_duration=30
)

# Get SRT Push URL for streaming
srt_url = channel_info["srt_push_url"]
print(f"Stream to: {srt_url}")
```

### Stopping a Live Stream

```python
# Stop the channel when done
await service.stop_channel(event_id="event-123")
```

### Monitoring Stream Status

```python
# Check channel status
status = await service.get_channel_status(event_id="event-123")
print(f"Status: {status}")
```

## Video Output

Video clips are stored in the configured cloud storage bucket with the following structure:

```
gs://{bucket-name}/events/{event-id}/captured/
  ├── segment_00001.ts
  ├── segment_00002.ts
  └── ...
```

Each segment has a duration configured by `VIDEO_CLIP_DURATION` parameter.

## Comparison with Current Solution

| Feature | Current (Python cv2) | New (Live Stream API) |
|---------|---------------------|----------------------|
| Video Capture | Local processing | Cloud-native |
| Storage | Local → Upload | Direct to cloud |
| Scalability | Single instance | Cloud-managed |
| Latency | Higher (local processing) | Lower (direct streaming) |
| Infrastructure | Requires compute | Serverless |
| Cost | Compute resources | Pay-per-use API |

## Benefits

1. **Reduced Infrastructure**: No need for dedicated video capture servers
2. **Direct Cloud Storage**: Eliminates local storage and upload steps
3. **Scalability**: Google manages stream processing infrastructure
4. **Reliability**: Built-in redundancy and failover
5. **Lower Latency**: Direct streaming to cloud storage

## Limitations

1. Requires Google Cloud Live Stream API (additional cost)
2. Network bandwidth requirements for SRT streaming
3. Regional availability of Live Stream API

## Future Enhancements

- Support for multiple concurrent streams
- Integration with existing detection pipeline
- Automatic cleanup of old video segments
- Real-time monitoring and alerting
- Support for additional input protocols (RTMP, WebRTC)
