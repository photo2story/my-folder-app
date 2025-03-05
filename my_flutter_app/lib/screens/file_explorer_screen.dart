// /my_flutter_app/lib/screens/file_explorer_screen.dart

import 'dart:convert';
import 'package:flutter/material.dart';
import '../services/file_explorer_service.dart';
import '../services/api_service.dart';
import 'package:intl/intl.dart'; // 이 줄은 유지하지만, Dart 3.x에서 오류가 발생하면 주석 처리

class FileExplorerScreen extends StatefulWidget {
  const FileExplorerScreen({super.key});

  @override
  State<FileExplorerScreen> createState() => _FileExplorerScreenState();
}

class _FileExplorerScreenState extends State<FileExplorerScreen> {
  final FileExplorerService _service = FileExplorerService();
  final ApiService _apiService = ApiService();
  Map<String, dynamic> _projectData = {};
  bool _loading = true;
  final ScrollController _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    _loadInitialData();
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _loadInitialData() async {
    print('Loading initial data...');
    setState(() => _loading = true);
    try {
      print('Fetching project audit data...');
      final data = await _apiService.fetchProjectAudit('20240178');
      print('Loaded project data: $data');
      
      setState(() {
        _projectData = data;
        _loading = false;
      });
      print('Data loaded successfully');
    } catch (e, stackTrace) {
      print('Error loading audit details: $e');
      print('Stack trace: $stackTrace');
      setState(() => _loading = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error loading audit: $e'),
            backgroundColor: Colors.red,
            duration: const Duration(seconds: 5),
          ),
        );
      }
    }
  }

  String _formatDate(DateTime? date) {
    if (date == null) return '';
    // intl ^0.20.2와 Dart 3.x 호환 문제로 오류 발생 시 아래 줄 주석 처리
    return DateFormat('yyyy-MM-dd HH:mm').format(date);
    // 임시 대체: 날짜를 기본 문자열로 변환
    // return date.toString();
  }

  Widget _buildDocumentList(String docType) {
    final docData = _projectData['documents']?[docType];
    if (docData == null || docData['exists'] == false) {
      return ListTile(
        leading: const Icon(Icons.cancel, color: Colors.red),
        title: Text('$docType: No documents found'),
      );
    }

    List<Map<String, dynamic>> details = [];
    var detailsList = docData['details'];
    if (detailsList is List) {
      for (var detail in detailsList) {
        if (detail is String) {
          try {
            // 문자열을 JSON으로 변환
            detail = jsonDecode(detail.replaceAll("'", '"'));
          } catch (e) {
            print('Error parsing detail: $e');
            detail = {'name': detail, 'path': detail};
          }
        }
        if (detail is Map) {
          details.add(Map<String, dynamic>.from(detail));
        }
      }
    }

    return Column(
      children: details.map((detail) {
        return Card(
          elevation: 0,
          margin: const EdgeInsets.symmetric(vertical: 2, horizontal: 8),
          child: ListTile(
            leading: SizedBox(
              width: 40,
              child: Center(child: _getFileIcon(detail['name'] ?? '')),
            ),
            title: Text(
              detail['name'] ?? 'Unknown',
              style: const TextStyle(fontSize: 14),
            ),
            subtitle: Text(
              detail['path'] ?? 'Unknown path',
              style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
            ),
            dense: true,
            horizontalTitleGap: 8,
          ),
        );
      }).toList(),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.blue.shade800,
        title: const Text(
          'Project Audit',
          style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, color: Colors.white),
            onPressed: _loadInitialData,
            tooltip: 'Refresh',
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : SingleChildScrollView(
              controller: _scrollController,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Padding(
                    padding: const EdgeInsets.all(16.0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Project ID: ${_projectData['project_id'] ?? 'N/A'}',
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'Department: ${_projectData['department'] ?? 'N/A'}',
                          style: const TextStyle(fontSize: 16),
                        ),
                        Text(
                          'Status: ${_projectData['status'] ?? 'N/A'}',
                          style: const TextStyle(fontSize: 16),
                        ),
                        Text(
                          'Contractor: ${_projectData['contractor'] ?? 'N/A'}',
                          style: const TextStyle(fontSize: 16),
                        ),
                      ],
                    ),
                  ),
                  const Divider(),
                  ExpansionTile(
                    title: const Text(
                      'Documents',
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    initiallyExpanded: true,
                    children: [
                      if (_projectData['documents'] != null)
                        ..._projectData['documents'].keys.map((String docType) {
                          return ExpansionTile(
                            title: Text(
                              docType,
                              style: const TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                            leading: Icon(
                              _projectData['documents'][docType]['exists']
                                  ? Icons.check_circle
                                  : Icons.cancel,
                              color: _projectData['documents'][docType]['exists']
                                  ? Colors.green
                                  : Colors.red,
                            ),
                            children: [_buildDocumentList(docType)],
                          );
                        }).toList(),
                    ],
                  ),
                ],
              ),
            ),
    );
  }

  Icon _getFileIcon(String filename) {
    final extension = filename.toLowerCase().split('.').last;
    switch (extension) {
      case 'pdf':
        return const Icon(Icons.picture_as_pdf, color: Colors.red);
      case 'doc':
      case 'docx':
        return const Icon(Icons.description, color: Colors.blue);
      case 'xls':
      case 'xlsx':
        return const Icon(Icons.table_chart, color: Colors.green);
      case 'hwp':
        return const Icon(Icons.description, color: Colors.purple);
      case 'jpg':
      case 'jpeg':
      case 'png':
      case 'gif':
        return const Icon(Icons.image, color: Colors.purple);
      case 'mp4':
      case 'avi':
      case 'mov':
        return const Icon(Icons.video_file, color: Colors.pink);
      case 'mp3':
      case 'wav':
        return const Icon(Icons.audio_file, color: Colors.orange);
      default:
        return const Icon(Icons.insert_drive_file, color: Colors.grey);
    }
  }
}