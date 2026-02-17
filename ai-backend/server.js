const express = require('express');
const cors = require('cors');
const multer = require('multer');
const OpenAI = require('openai');
const rateLimit = require('express-rate-limit');
const swaggerJsdoc = require('swagger-jsdoc');
const swaggerUi = require('swagger-ui-express');
require('dotenv').config();

const app = express();

// Rate limiting
const limiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100 // limit each IP to 100 requests per windowMs
});

// Middleware
app.use(cors({
  origin: 'http://localhost:3000',
  credentials: true
}));
app.use(express.json());
app.use(limiter);

// Swagger configuration
const swaggerOptions = {
  definition: {
    openapi: '3.0.0',
    info: {
      title: 'AgroCare AI API',
      version: '1.0.0',
      description: 'AI backend for AgroCare - Plant disease detection and farming advice',
      contact: {
        name: 'AgroCare Support',
        email: 'support@agrocare.com'
      },
    },
    servers: [
      {
        url: 'http://localhost:5000',
        description: 'Development server'
      },
    ],
    components: {
      schemas: {
        ChatRequest: {
          type: 'object',
          required: ['message'],
          properties: {
            message: {
              type: 'string',
              description: 'The user\'s question or message',
              example: 'What crops grow well in Rwanda?'
            }
          }
        },
        ChatResponse: {
          type: 'object',
          properties: {
            response: {
              type: 'string',
              description: 'AI response message',
              example: 'In Rwanda, common crops include maize, beans, potatoes, and coffee...'
            }
          }
        },
        ErrorResponse: {
          type: 'object',
          properties: {
            error: {
              type: 'string',
              description: 'Error message',
              example: 'Failed to process request'
            },
            message: {
              type: 'string',
              description: 'Detailed error message',
              example: 'OpenAI API error'
            }
          }
        },
        HealthResponse: {
          type: 'object',
          properties: {
            status: {
              type: 'string',
              example: 'ok'
            },
            message: {
              type: 'string',
              example: 'AI backend is running'
            },
            timestamp: {
              type: 'string',
              format: 'date-time',
              example: '2024-01-01T00:00:00.000Z'
            }
          }
        }
      },
      securitySchemes: {
        ApiKeyAuth: {
          type: 'apiKey',
          in: 'header',
          name: 'X-API-Key'
        }
      }
    },
    tags: [
      {
        name: 'Health',
        description: 'Health check endpoints'
      },
      {
        name: 'Chat',
        description: 'Text chat endpoints'
      },
      {
        name: 'Image Analysis',
        description: 'Plant image analysis endpoints'
      }
    ]
  },
  apis: ['./server.js'], // Path to the API docs
};

const swaggerSpec = swaggerJsdoc(swaggerOptions);

// Serve Swagger UI
app.use('/api-docs', swaggerUi.serve, swaggerUi.setup(swaggerSpec, {
  explorer: true,
  customCss: '.swagger-ui .topbar { display: none }',
  customSiteTitle: 'AgroCare AI API Documentation'
}));

// Serve Swagger JSON
app.get('/api-docs.json', (req, res) => {
  res.setHeader('Content-Type', 'application/json');
  res.send(swaggerSpec);
});

// Configure multer for file uploads
const upload = multer({
  limits: {
    fileSize: 5 * 1024 * 1024, // 5MB limit
  },
  storage: multer.memoryStorage(),
  fileFilter: (req, file, cb) => {
    if (file.mimetype.startsWith('image/')) {
      cb(null, true);
    } else {
      cb(new Error('Only images are allowed'));
    }
  }
});

// Initialize OpenAI
const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

/**
 * @swagger
 * /api/health:
 *   get:
 *     summary: Check if the API is running
 *     tags: [Health]
 *     responses:
 *       200:
 *         description: API is healthy
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/HealthResponse'
 */
app.get('/api/health', (req, res) => {
  res.json({ 
    status: 'ok', 
    message: 'AI backend is running',
    timestamp: new Date().toISOString()
  });
});

/**
 * @swagger
 * /api/ai/chat:
 *   post:
 *     summary: Send a text message to the AI
 *     tags: [Chat]
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             $ref: '#/components/schemas/ChatRequest'
 *     responses:
 *       200:
 *         description: Successful response
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/ChatResponse'
 *       400:
 *         description: Bad request
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/ErrorResponse'
 *       500:
 *         description: Server error
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/ErrorResponse'
 */
app.post('/api/ai/chat', async (req, res) => {
  try {
    const { message } = req.body;

    if (!message) {
      return res.status(400).json({ error: 'Message is required' });
    }

    console.log('Processing message:', message);

    const completion = await openai.chat.completions.create({
      model: "gpt-3.5-turbo",
      messages: [
        {
          role: "system",
          content: "You are AgroCare AI, a helpful assistant for farmers in Rwanda and East Africa. You provide practical advice on crop diseases, pests, farming techniques, and agricultural best practices. Keep responses concise, practical, and easy to understand. Use local context when relevant."
        },
        {
          role: "user",
          content: message
        }
      ],
      max_tokens: 500,
      temperature: 0.7,
    });

    const aiResponse = completion.choices[0].message.content;
    console.log('AI Response:', aiResponse);

    res.json({ response: aiResponse });

  } catch (error) {
    console.error('OpenAI API Error:', error);
    
    if (error.response) {
      res.status(error.response.status).json({ 
        error: 'OpenAI API error', 
        details: error.response.data 
      });
    } else {
      res.status(500).json({ 
        error: 'Failed to process request',
        message: error.message 
      });
    }
  }
});

/**
 * @swagger
 * /api/ai/analyze-image:
 *   post:
 *     summary: Analyze a plant image for diseases
 *     tags: [Image Analysis]
 *     requestBody:
 *       required: true
 *       content:
 *         multipart/form-data:
 *           schema:
 *             type: object
 *             required:
 *               - image
 *             properties:
 *               image:
 *                 type: string
 *                 format: binary
 *                 description: Plant image file (JPEG, PNG, etc.) - max 5MB
 *               message:
 *                 type: string
 *                 description: Optional additional context or question
 *                 example: "What's wrong with my maize leaves?"
 *     responses:
 *       200:
 *         description: Successful analysis
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/ChatResponse'
 *       400:
 *         description: Bad request - missing image or invalid file
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/ErrorResponse'
 *       500:
 *         description: Server error
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/ErrorResponse'
 */
app.post('/api/ai/analyze-image', upload.single('image'), async (req, res) => {
  try {
    const { message } = req.body;
    const imageFile = req.file;

    if (!imageFile) {
      return res.status(400).json({ error: 'Image is required' });
    }

    console.log('Analyzing image:', imageFile.originalname);
    console.log('Image size:', imageFile.size);
    console.log('Image type:', imageFile.mimetype);

    // Convert image to base64
    const base64Image = imageFile.buffer.toString('base64');
    const imageUrl = `data:${imageFile.mimetype};base64,${base64Image}`;

    const completion = await openai.chat.completions.create({
      model: "gpt-4-vision-preview",
      messages: [
        {
          role: "system",
          content: "You are a plant disease detection expert. Analyze the plant image and provide: 1) What disease or pest you detect 2) Confidence level 3) Description of the problem 4) Treatment recommendations. Be practical and use simple language for farmers. If you cannot identify the plant or disease clearly, say so and suggest what to look for in a better image."
        },
        {
          role: "user",
          content: [
            { 
              type: "text", 
              text: message || "Analyze this plant image for diseases, pests, or other issues. What's wrong and how can I treat it?" 
            },
            {
              type: "image_url",
              image_url: {
                url: imageUrl,
              },
            },
          ],
        },
      ],
      max_tokens: 800,
      temperature: 0.3,
    });

    const analysis = completion.choices[0].message.content;
    console.log('Analysis complete');

    res.json({ response: analysis });

  } catch (error) {
    console.error('Image Analysis Error:', error);
    
    if (error.response) {
      res.status(error.response.status).json({ 
        error: 'OpenAI API error', 
        details: error.response.data 
      });
    } else {
      res.status(500).json({ 
        error: 'Failed to analyze image',
        message: error.message 
      });
    }
  }
});

// Error handling middleware
app.use((err, req, res, next) => {
  console.error('Server Error:', err);
  
  if (err instanceof multer.MulterError) {
    if (err.code === 'LIMIT_FILE_SIZE') {
      return res.status(400).json({ error: 'File too large. Max size is 5MB' });
    }
    return res.status(400).json({ error: err.message });
  }
  
  if (err.message === 'Only images are allowed') {
    return res.status(400).json({ error: err.message });
  }
  
  res.status(500).json({ 
    error: 'Server error',
    message: err.message 
  });
});

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => {
  console.log(`✅ AI backend running on http://localhost:${PORT}`);
  console.log(`📚 Swagger documentation: http://localhost:${PORT}/api-docs`);
  console.log(`📝 Available endpoints:`);
  console.log(`   - GET  /api/health`);
  console.log(`   - POST /api/ai/chat`);
  console.log(`   - POST /api/ai/analyze-image`);
  console.log(`   - GET  /api-docs (Swagger UI)`);
  console.log(`   - GET  /api-docs.json (Swagger JSON)`);
});