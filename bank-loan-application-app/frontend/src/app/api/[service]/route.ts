import { NextRequest, NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ service: string }> }
): Promise<Response> {
  try {
    const { service } = await params;
    
    // Validate service name to prevent directory traversal
    if (!/^[a-zA-Z0-9_-]+$/.test(service)) {
      return NextResponse.json({ error: 'Invalid service name' }, { status: 400 });
    }

    const requestBody = await request.json();
    
    // Path to the microservices directory (2 levels up from frontend root)
    const microservicesDir = path.resolve(process.cwd(), '../../microservices', service);
    
    if (!fs.existsSync(microservicesDir) || !fs.existsSync(path.join(microservicesDir, 'lambda_function.py'))) {
      return NextResponse.json({ error: `Service ${service} not found locally` }, { status: 404 });
    }

    // Format the payload exactly as AWS API Gateway would send it to Lambda
    const eventPayload = JSON.stringify({
      body: JSON.stringify(requestBody),
      headers: Object.fromEntries(request.headers),
    });

    // We use a python one-liner to import the lambda, run it, and print the result with a delimiter
    const pythonCode = `
import sys, json
sys.path.append('.')
import lambda_function
event = json.loads(sys.argv[1])
context = type('Context', (), {'aws_request_id': 'local-dev-' + str(id(event))})()
result = lambda_function.lambda_handler(event, context)
print('\\n===RESULT===\\n')
print(json.dumps(result))
`;

    return new Promise<Response>((resolve) => {
      const pyProcess = spawn('python', ['-c', pythonCode, eventPayload], {
        cwd: microservicesDir,
      });

      let stdoutData = '';
      let stderrData = '';

      pyProcess.stdout.on('data', (data) => {
        stdoutData += data.toString();
      });

      pyProcess.stderr.on('data', (data) => {
        stderrData += data.toString();
      });

      pyProcess.on('close', (code) => {
        if (code !== 0) {
          console.error(`[${service}] Python error:`, stderrData);
          resolve(NextResponse.json({ error: 'Internal Server Error', details: stderrData }, { status: 500 }));
          return;
        }

        // Parse the stdout to extract the result
        const parts = stdoutData.split(/===RESULT===\r?\n/);
        
        // Log the lambda debug output for visibility in dev console
        if (parts[0].trim()) {
          console.log(`[${service} Logs]:\n`, parts[0].trim());
        }

        try {
          const resultStr = parts[parts.length - 1].trim();
          const lambdaResult = JSON.parse(resultStr);
          
          // API Gateway returns the body as a JSON string
          const responseBody = typeof lambdaResult.body === 'string' 
            ? JSON.parse(lambdaResult.body) 
            : lambdaResult.body;
            
          resolve(NextResponse.json(responseBody, { status: lambdaResult.statusCode || 200 }));
        } catch {
          console.error(`[${service}] Failed to parse lambda output:`, parts[parts.length - 1]);
          resolve(NextResponse.json({ error: 'Invalid lambda response format' }, { status: 500 }));
        }
      });
    });

  } catch (error: unknown) {
    console.error('API Route Error:', error);
    return NextResponse.json({ error: error instanceof Error ? error.message : 'Unknown API route error' }, { status: 500 });
  }
}
