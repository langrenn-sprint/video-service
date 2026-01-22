# Setup Guide for Google Live Stream API Integration

This guide walks you through setting up the Google Live Stream API for video capture.

## Prerequisites

1. **Google Cloud Project**
   - Active GCP project
   - Billing enabled
   - Live Stream API enabled

2. **Service Account**
   - With appropriate permissions
   - JSON key file downloaded

3. **Cloud Storage Bucket**
   - Created and accessible
   - Appropriate lifecycle policies configured

## Step 1: Enable Google Cloud Live Stream API

```bash
# Set your project ID
export PROJECT_ID="your-project-id"

# Enable the Live Stream API
gcloud services enable livestream.googleapis.com --project=$PROJECT_ID
```

## Step 2: Create Service Account

```bash
# Create service account
gcloud iam service-accounts create video-streaming-sa \
    --description="Service account for video streaming" \
    --display-name="Video Streaming Service Account" \
    --project=$PROJECT_ID

# Grant necessary permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:video-streaming-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/livestream.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:video-streaming-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/storage.objectAdmin"

# Create and download key
gcloud iam service-accounts keys create ~/video-streaming-key.json \
    --iam-account=video-streaming-sa@${PROJECT_ID}.iam.gserviceaccount.com
```

## Step 3: Create Cloud Storage Bucket (if needed)

```bash
# Set bucket name
export BUCKET_NAME="langrenn-sprint"
export REGION="europe-north1"

# Create bucket (skip if already exists)
gcloud storage buckets create gs://$BUCKET_NAME \
    --location=$REGION \
    --project=$PROJECT_ID

# Grant service account access
gcloud storage buckets add-iam-policy-binding gs://$BUCKET_NAME \
    --member="serviceAccount:video-streaming-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/storage.objectAdmin"
```

## Step 4: Configure Authentication

Set the environment variable to use the service account:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/video-streaming-key.json"
```

Add this to your `.bashrc` or `.zshrc` for persistence:

```bash
echo 'export GOOGLE_APPLICATION_CREDENTIALS="$HOME/video-streaming-key.json"' >> ~/.bashrc
```

## Step 5: Install Dependencies

```bash
cd /path/to/video-service

# Install the new dependency
uv add google-cloud-video-live-stream>=1.8.0

# Or manually install
pip install google-cloud-video-live-stream>=1.8.0
```

## Step 6: Configure Video Streaming

Edit the configuration file at `video-streaming/config/livestream_settings.json`:

```json
{
    "GOOGLE_CLOUD_PROJECT": "your-project-id",
    "GOOGLE_CLOUD_REGION": "europe-north1",
    "GOOGLE_STORAGE_BUCKET": "langrenn-sprint",
    "VIDEO_CLIP_DURATION": 30,
    "SRT_PORT": 5000,
    "LIVESTREAM_CHANNEL_PREFIX": "video-capture",
    "LIVESTREAM_INPUT_PREFIX": "srt-input",
    "LIVESTREAM_OUTPUT_PREFIX": "gcs-output",
    "VIDEO_OUTPUT_PATH_TEMPLATE": "events/{event_id}/captured/",
    "SEGMENT_DURATION_SECONDS": 30
}
```

Or use environment variables:

```bash
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GOOGLE_CLOUD_REGION="europe-north1"
export GOOGLE_STORAGE_BUCKET="langrenn-sprint"
export VIDEO_CLIP_DURATION=30
```

## Step 7: Test the Setup

Run the example script to verify everything is working:

```bash
# Set required environment variables
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GOOGLE_CLOUD_REGION="europe-north1"
export GOOGLE_STORAGE_BUCKET="langrenn-sprint"
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/video-streaming-key.json"

# Run the example
python -m video_streaming.examples.basic_usage
```

## Step 8: Stream Video

Once the channel is created, you'll receive an SRT Push URL. Use FFmpeg to stream:

```bash
# Stream from a file
ffmpeg -re -i input.mp4 -c copy -f mpegts 'srt://your-input-url?streamid=your-stream-id'

# Stream from a camera
ffmpeg -f v4l2 -i /dev/video0 -c:v libx264 -preset veryfast -b:v 2000k -f mpegts 'srt://your-input-url?streamid=your-stream-id'

# Stream from RTSP source
ffmpeg -i rtsp://camera-ip/stream -c:v libx264 -preset veryfast -b:v 2000k -f mpegts 'srt://your-input-url?streamid=your-stream-id'
```

## Step 9: Monitor and Verify

### Check Channel Status

```python
from video_streaming.services import LiveStreamService

service = LiveStreamService()
status = await service.get_channel_status(event_id="your-event-id")
print(f"Status: {status['state']}")
```

### List Active Channels

```python
channels = await service.list_active_channels()
for ch in channels:
    print(f"Event: {ch['event_id']}, State: {ch['state']}")
```

### Check Output Files

```bash
# List files in the bucket
gsutil ls gs://$BUCKET_NAME/events/your-event-id/captured/

# Download a segment
gsutil cp gs://$BUCKET_NAME/events/your-event-id/captured/segment_00001.ts ./
```

## Step 10: Cleanup

When done testing, clean up resources:

```python
from video_streaming.services import LiveStreamService

service = LiveStreamService()
await service.stop_channel(event_id="your-event-id")
await service.cleanup_resources(event_id="your-event-id")
```

## Troubleshooting

### Error: "API has not been enabled"

Enable the API:
```bash
gcloud services enable livestream.googleapis.com --project=$PROJECT_ID
```

### Error: "Permission denied"

Check service account permissions:
```bash
gcloud projects get-iam-policy $PROJECT_ID \
    --flatten="bindings[].members" \
    --filter="bindings.members:serviceAccount:video-streaming-sa@${PROJECT_ID}.iam.gserviceaccount.com"
```

### Error: "Bucket does not exist"

Create the bucket or check the name:
```bash
gsutil ls gs://$BUCKET_NAME
```

### Channel stuck in "STARTING" state

This can take 5-10 minutes. Check status:
```bash
gcloud livestream channels describe video-capture-your-event-id \
    --location=$REGION \
    --project=$PROJECT_ID
```

### No video segments appearing

1. Verify FFmpeg is streaming correctly
2. Check channel logs in Cloud Console
3. Verify SRT URL is correct
4. Ensure stream format is compatible (H.264 video, AAC audio)

## Production Deployment

### Recommended Settings

1. **Regions**: Use a region close to your video source
2. **Bucket Lifecycle**: Configure lifecycle policies to manage storage costs
3. **Monitoring**: Set up Cloud Monitoring alerts for channel status
4. **Logging**: Enable detailed logging for debugging

### Lifecycle Policy for Auto-deletion

Create `lifecycle.json`:

```json
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {
          "age": 30,
          "matchesPrefix": ["events/"]
        }
      }
    ]
  }
}
```

Apply it:

```bash
gsutil lifecycle set lifecycle.json gs://$BUCKET_NAME
```

### Cost Optimization

1. Use appropriate resolution (720p vs 1080p)
2. Configure segment duration based on needs
3. Implement automatic channel cleanup
4. Use bucket lifecycle policies
5. Monitor API usage

### Security Best Practices

1. Use service accounts with minimal permissions
2. Rotate service account keys regularly
3. Use VPC Service Controls if available
4. Enable bucket versioning for important events
5. Implement access logging

## Integration with Existing System

To integrate with the existing video-service:

```python
# In your app.py or worker
from video_service.services import VideoService
from video_streaming.services import LiveStreamService

async def capture_video_handler(event):
    # Choose based on configuration
    if event.get("use_live_stream_api"):
        service = LiveStreamService()
        return await service.create_and_start_channel(
            event_id=event["id"],
            clip_duration=30
        )
    else:
        service = VideoService()
        return await service.capture_video(
            token=token,
            event=event,
            status_type="video_status",
            instance_name="worker-1"
        )
```

## Support and Resources

- [Google Live Stream API Documentation](https://cloud.google.com/video-live-stream/docs)
- [Python Client Library](https://cloud.google.com/python/docs/reference/livestream/latest)
- [FFmpeg SRT Streaming Guide](https://trac.ffmpeg.org/wiki/StreamingGuide)
- [SRT Protocol Documentation](https://github.com/Haivision/srt)

## Next Steps

1. Test with various input sources
2. Monitor costs and optimize settings
3. Integrate with detection pipeline
4. Set up automated cleanup
5. Configure monitoring and alerts