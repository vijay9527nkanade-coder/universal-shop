import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';
import 'package:url_launcher/url_launcher.dart';
import '../activity_tracker.dart';

class LensScreen extends StatefulWidget {
  const LensScreen({super.key});

  @override
  State<LensScreen> createState() => _LensScreenState();
}

class _LensScreenState extends State<LensScreen> {
  final ImagePicker _picker = ImagePicker();
  File? _imageFile;
  bool _isLoading = false;
  List<dynamic> _results = [];
  String _errorMessage = '';
  bool _hasSearched = false;

  // Use 127.0.0.1 for Android Emulator connecting to localhost backend.
  // For iOS Simulator, use 127.0.0.1.
  final String _baseUrl = 'http://127.0.0.1:8000/api/v1';

  Future<void> _pickImage(ImageSource source) async {
    try {
      final pickedFile = await _picker.pickImage(source: source);
      if (pickedFile != null) {
        setState(() {
          _imageFile = File(pickedFile.path);
        });
        _performLensSearch();
      }
    } catch (e) {
      setState(() {
        _errorMessage = 'Failed to pick image: $e';
      });
    }
  }

  Future<void> _performLensSearch() async {
    if (_imageFile == null) return;

    ActivityTracker.logLens();

    setState(() {
      _isLoading = true;
      _errorMessage = '';
      _results = [];
      _hasSearched = true;
    });

    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$_baseUrl/lens'),
      );
      
      request.files.add(
        await http.MultipartFile.fromPath(
          'file',
          _imageFile!.path,
        ),
      );

      final streamedResponse = await request.send();
      final response = await http.Response.fromStream(streamedResponse);
      
      if (response.statusCode == 200) {
        setState(() {
          _results = json.decode(response.body);
          _isLoading = false;
        });
      } else {
        setState(() {
          _errorMessage = 'Server error: ${response.statusCode}\n${response.body}';
          _isLoading = false;
        });
      }
    } catch (e) {
      setState(() {
        _errorMessage = 'Failed to connect to backend: $e\n(Make sure backend is running on port 8000)';
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Visual Search (Lens)'),
        elevation: 2,
        actions: [
          IconButton(
            icon: const Icon(Icons.camera_alt),
            onPressed: () => _pickImage(ImageSource.camera),
            tooltip: 'Take a Photo',
          ),
          IconButton(
            icon: const Icon(Icons.photo_library),
            onPressed: () => _pickImage(ImageSource.gallery),
            tooltip: 'Pick from Gallery',
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            if (_imageFile != null) ...[
              Container(
                height: 150,
                width: double.infinity,
                decoration: BoxDecoration(
                  border: Border.all(color: Colors.grey),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(8),
                  child: Image.file(_imageFile!, fit: BoxFit.cover),
                ),
              ),
              const SizedBox(height: 16),
            ],
            if (_isLoading)
              const Expanded(
                child: Center(
                  child: CircularProgressIndicator(),
                ),
              )
            else if (_errorMessage.isNotEmpty)
              Expanded(
                child: Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.error_outline, color: Colors.red, size: 48),
                      const SizedBox(height: 16),
                      Text(
                        'Oops, something went wrong!',
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      const SizedBox(height: 8),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 32.0),
                        child: Text(
                          _errorMessage,
                          style: const TextStyle(color: Colors.grey),
                          textAlign: TextAlign.center,
                        ),
                      ),
                      const SizedBox(height: 16),
                      ElevatedButton.icon(
                        onPressed: _performLensSearch,
                        icon: const Icon(Icons.refresh),
                        label: const Text('Try Again'),
                      ),
                    ],
                  ),
                ),
              )
            else if (_hasSearched && _results.isEmpty)
              Expanded(
                child: Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.search_off, color: Colors.grey[400], size: 64),
                      const SizedBox(height: 16),
                      Text(
                        'No matches found.',
                        style: Theme.of(context).textTheme.titleLarge?.copyWith(color: Colors.grey[600]),
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        'Try taking a clearer photo.',
                        style: TextStyle(color: Colors.grey),
                      ),
                    ],
                  ),
                ),
              )
            else if (_results.isNotEmpty)
              Expanded(
                child: ListView.builder(
                  itemCount: _results.length,
                  itemBuilder: (context, index) {
                    final product = _results[index];
                    return Card(
                      margin: const EdgeInsets.only(bottom: 12),
                      clipBehavior: Clip.antiAlias,
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          // Product Image
                          SizedBox(
                            width: 100,
                            height: 120,
                            child: product['image_url'] != null 
                              ? Image.network(
                                  product['image_url'], 
                                  fit: BoxFit.cover,
                                  errorBuilder: (c, e, s) => const Icon(Icons.image_not_supported, size: 50, color: Colors.grey),
                                )
                              : const Icon(Icons.image, size: 50, color: Colors.grey),
                          ),
                          
                          // Product Details
                          Expanded(
                            child: Padding(
                              padding: const EdgeInsets.all(12.0),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    product['name'] ?? 'Unknown', 
                                    maxLines: 2, 
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                                  ),
                                  const SizedBox(height: 8),
                                  Text(
                                    '${product['platform'].toString().toUpperCase()} • ₹${product['price'] ?? 'N/A'}',
                                    style: const TextStyle(color: Colors.green, fontWeight: FontWeight.bold),
                                  ),
                                  const SizedBox(height: 4),
                                  Wrap(
                                    crossAxisAlignment: WrapCrossAlignment.center,
                                    spacing: 8,
                                    children: [
                                      Text(
                                        'Rating: ${product['rating'] ?? 'N/A'} ★ (${product['review_count'] ?? 0} reviews)',
                                        style: TextStyle(color: Colors.grey[700], fontSize: 13),
                                      ),
                                      if (product['sentiment_score'] != null)
                                        Builder(
                                          builder: (context) {
                                            final double score = (product['sentiment_score'] as num).toDouble();
                                            final bool isPositive = score > 0.05;
                                            final bool isNegative = score < -0.05;
                                            final String label = isPositive ? 'Positive' : (isNegative ? 'Negative' : 'Neutral');
                                            final Color bgColor = isPositive ? Colors.green : (isNegative ? Colors.red : Colors.grey);
                                            return Chip(
                                              label: Text(label, style: const TextStyle(fontSize: 10, color: Colors.white)),
                                              backgroundColor: bgColor,
                                              visualDensity: VisualDensity.compact,
                                            );
                                          },
                                        ),
                                    ],
                                  ),
                                  const SizedBox(height: 8),
                                  Row(
                                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                    children: [
                                      Row(
                                        children: [
                                          if (product['is_fallback'] == true)
                                            const Chip(
                                              label: Text('Fallback', style: TextStyle(fontSize: 10, color: Colors.white)),
                                              backgroundColor: Colors.orange,
                                              visualDensity: VisualDensity.compact,
                                            )
                                          else if (product['similarity_score'] != null)
                                            Chip(
                                              label: Text('Sim: ${product['similarity_score'].toStringAsFixed(2)}', style: const TextStyle(fontSize: 10)),
                                              backgroundColor: Colors.purple[100],
                                              visualDensity: VisualDensity.compact,
                                            )
                                          else if (product['rank_score'] != null)
                                            Chip(
                                              label: Text('Score: ${product['rank_score'].toStringAsFixed(2)}', style: const TextStyle(fontSize: 10)),
                                              backgroundColor: Colors.blue[100],
                                              visualDensity: VisualDensity.compact,
                                            ),
                                        ],
                                      ),
                                      // Buy Button
                                      TextButton.icon(
                                        onPressed: () async {
                                          final productId = product['id'] as int?;
                                          if (productId != null) {
                                            ActivityTracker.logClick(productId);
                                          }
                                          final url = product['product_url']?.toString() ?? '';
                                          if (url.isNotEmpty) {
                                            final uri = Uri.parse(url);
                                            if (await canLaunchUrl(uri)) {
                                              await launchUrl(uri, mode: LaunchMode.externalApplication);
                                            } else {
                                              if (context.mounted) {
                                                ScaffoldMessenger.of(context).showSnackBar(
                                                  SnackBar(content: Text('Could not open link: $url')),
                                                );
                                              }
                                            }
                                          }
                                        },
                                        icon: const Icon(Icons.open_in_new, size: 16),
                                        label: Text(
                                          'Buy on ${product['platform']?.toString().toUpperCase() ?? ''}',
                                          style: const TextStyle(fontSize: 12),
                                        ),
                                        style: TextButton.styleFrom(
                                          visualDensity: VisualDensity.compact,
                                          padding: const EdgeInsets.symmetric(horizontal: 8),
                                        ),
                                      ),
                                    ],
                                  )
                                ],
                              ),
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
              )
            else
              const Expanded(
                child: Center(
                  child: Text('Take a photo or pick an image to search products.'),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
