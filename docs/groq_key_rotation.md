# Groq API Key Rotation System

## 🎯 Overview

SYNAPSE v3.0 includes an **automatic Groq API key rotation system** that supports multiple keys with load balancing and failure recovery.

## 🔄 Key Rotation Features

### **Multi-Key Support**
- **Primary Key**: `GROQ_API_KEY` - Main API key
- **Additional Keys**: `GROQ_API_KEY_1`, `GROQ_API_KEY_2`, etc. - Up to 11 total keys
- **Automatic Detection**: System loads all available keys from environment
- **Round-Robin Load**: Distributes requests across healthy keys

### **Health Monitoring**
- **Real-time Health**: Each key is checked before use
- **Error Tracking**: Failed requests mark keys as unhealthy
- **Cooldown Management**: Automatic cooldown for failed keys
- **Status Tracking**: Active, Depleted, Error, Cooldown states

### **Automatic Recovery**
- **Failure Detection**: Keys marked unhealthy after 5 consecutive failures
- **Cooldown Period**: 10 minutes for error keys, 1 hour for depleted keys
- **Auto-Reactivation**: Keys automatically return to active state
- **TPM Reset**: Hourly token limit reset

## 🛠️ Configuration

### **Environment Variables**
```bash
# Primary key (required)
GROQ_API_KEY=gsk_your_primary_key

# Additional keys (optional)
GROQ_API_KEY_1=gsk_your_secondary_key
GROQ_API_KEY_2=gsk_your_tertiary_key
GROQ_API_KEY_3=gsk_your_fourth_key
# ... up to GROQ_API_KEY_10
```

### **Key Limits**
- **TPM Limit**: 30,000 tokens per minute per key (Llama 4 Scout)
- **Concurrent Usage**: All keys can be used simultaneously
- **Rotation Strategy**: Round-robin with health checks
- **Fallback**: If all keys fail, system waits and retries

## 📊 Monitoring Endpoints

### **Key Status Dashboard**
```bash
GET /api/v1/groq/status
```

**Returns:**
```json
{
  "service": "Groq Key Manager",
  "version": "1.0.0",
  "total_keys": 4,
  "active_keys": 3,
  "depleted_keys": 0,
  "error_keys": 1,
  "cooldown_keys": 0,
  "total_tpm_available": 90000,
  "keys": [
    {
      "key_id": "primary",
      "status": "active",
      "current_tpm": 1250,
      "tpm_limit": 30000,
      "tpm_remaining": 28750,
      "last_used": "2025-05-12T12:30:00Z",
      "error_count": 0,
      "cooldown_until": null
    }
  ]
}
```

### **Force Rotation**
```bash
GET /api/v1/groq/rotate
```

**Returns:**
```json
{
  "message": "Key rotation forced - next API call will use different key",
  "current_index": 2
}
```

### **Reset Limits**
```bash
POST /api/v1/groq/reset
```

**Returns:**
```json
{
  "message": "All key limits have been reset",
  "timestamp": "2025-05-12T12:30:00Z"
}
```

## 🔧 Usage Examples

### **Basic Usage**
```python
from api.groq_manager import get_groq_manager, with_groq_rotation

# Get a client with automatic rotation
@with_groq_rotation
async def my_query_function():
    manager = get_groq_manager()
    client = await manager.get_client()
    
    # Use client normally - rotation is automatic
    response = client.chat.completions.create(
        model="llama-4-scout-17b",
        messages=[{"role": "user", "content": "Hello SYNAPSE!"}]
    )
    
    return response.choices[0].message.content
```

### **Direct Key Management**
```python
from api.groq_manager import get_groq_manager

manager = get_groq_manager()

# Get key statistics
stats = manager.get_key_stats()
print(f"Total keys: {stats['total_keys']}")
print(f"Active keys: {stats['active_keys']}")

# Get specific key
key = await manager.get_next_key()
print(f"Using key: {key.key_id} (TPM: {key.current_tpm}/{key.tpm_limit})")
```

## 🚨 Key States

### **Active** ✅
- Available for use
- Within TPM limits
- No errors in last hour
- Health check passed

### **Depleted** ⚠️
- Reached TPM limit
- Waits for hourly reset
- Automatically reactivates after reset

### **Error** ❌
- 5+ consecutive failures
- In cooldown for 10 minutes
- Marked for manual review

### **Cooldown** ⏸️
- Temporary unavailability
- Automatic recovery after cooldown period
- Used for rate limiting and error recovery

## 🔄 Rotation Algorithm

1. **Health Check**: Verify key is responsive and within limits
2. **Round-Robin**: Try next key in sequence
3. **Fallback**: If all keys unhealthy, use primary anyway
4. **Recovery**: Automatically reactivate keys when conditions met
5. **Reset**: Hourly TPM limits for all keys

## 📈 Benefits

### **Increased Throughput**
- **11x Capacity**: With 11 keys at 30K TPM each = 330K TPM total
- **No Downtime**: Failed keys automatically rotated out
- **Load Balancing**: Even distribution across all keys

### **Reliability**
- **Fault Tolerance**: Single key failure doesn't affect service
- **Auto-Recovery**: Keys automatically return when healthy
- **Monitoring**: Complete visibility into key performance

### **Cost Efficiency**
- **Optimized Usage**: Even distribution prevents hot keys
- **Waste Reduction**: Depleted keys automatically rested
- **Budget Control**: Clear visibility into API consumption

## 🛠️ Troubleshooting

### **Common Issues**

#### **All Keys in Error State**
```bash
# Check system status
curl http://localhost:8000/api/v1/groq/status

# Force reset if needed
curl -X POST http://localhost:8000/api/v1/groq/reset
```

#### **Key Not Rotating**
```bash
# Check key configuration
grep GROQ_API_KEY .env

# Verify environment variables
env | grep GROQ_API_KEY
```

#### **High Error Rates**
```bash
# Check logs for specific errors
grep "Groq API call failed" logs/synapse.log

# Monitor key statistics
curl http://localhost:8000/api/v1/groq/status | jq '.keys[] | select(.error_count > 0)'
```

### **Debug Mode**
Add to `.env`:
```bash
LOG_LEVEL=DEBUG
```

This provides detailed logging for:
- Key selection decisions
- Health check results
- Rotation events
- Error analysis

## 🔐 Security

### **Key Protection**
- **Environment Variables**: Keys stored securely in environment
- **No Logging**: API keys never logged in plain text
- **Rotation**: Regular key rotation reduces exposure risk
- **Access Control**: Separate keys for different environments

### **Best Practices**
1. **Use Environment Variables**: Never hardcode keys in source
2. **Regular Rotation**: Change keys every 30 days
3. **Monitor Usage**: Watch for unusual consumption patterns
4. **Separate Environments**: Different keys for dev/staging/production
5. **Secure Storage**: Use secure credential management systems

## 📊 Performance Metrics

### **Monitoring Dashboard**
Track these metrics in your monitoring system:

- **Key Utilization**: TPM usage per key
- **Error Rates**: Failure percentage per key
- **Rotation Frequency**: How often keys are rotated
- **Response Times**: Latency per key
- **Success Rates**: Request success percentage

### **Alert Thresholds**
Set up alerts for:
- **Error Rate > 10%**: Investigate key issues
- **TPM Usage > 80%**: Risk of depletion
- **All Keys Error**: Critical system alert
- **Cooldown Keys > 50%**: Service degradation

---

**The Groq key rotation system ensures SYNAPSE can handle high-volume workloads while maintaining reliability and cost efficiency.**
