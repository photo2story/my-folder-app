// /my_flutter_app/lib/screens/file_explorer_screen.dart

import 'dart:convert';
import 'package:flutter/material.dart';
import '../services/file_explorer_service.dart';
import '../services/api_service.dart';
import '../models/project_model.dart';
import 'package:intl/intl.dart';

class FileExplorerScreen extends StatefulWidget {
  const FileExplorerScreen({super.key});

  @override
  State<FileExplorerScreen> createState() => _FileExplorerScreenState();
}

class _FileExplorerScreenState extends State<FileExplorerScreen> {
  final ApiService _apiService = ApiService();
  ProjectModel? _projectData;
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
      print('Fetching project audit data for project 20240178...');
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
            content: Text('데이터 로드 중 오류 발생: $e'),
            backgroundColor: Colors.red,
            duration: const Duration(seconds: 5),
          ),
        );
      }
    }
  }

  String _formatDate(DateTime? date) {
    if (date == null) return '날짜 없음';
    try {
      return DateFormat('yyyy-MM-dd HH:mm').format(date);
    } catch (e) {
      return date.toString();
    }
  }

  Widget _buildDocumentList(String docType) {
    if (_projectData == null || _projectData!.documents[docType] == null) {
      return ListTile(
        leading: const Icon(Icons.error_outline, color: Colors.orange),
        title: Text('$docType: 문서 정보를 찾을 수 없습니다'),
      );
    }

    final docData = _projectData!.documents[docType]!;
    if (docData['exists'] != true) {
      return ListTile(
        leading: const Icon(Icons.cancel, color: Colors.red),
        title: Text('$docType: 문서가 존재하지 않습니다'),
      );
    }

    List<Map<String, dynamic>> details = [];
    var detailsList = docData['details'];
    if (detailsList is List) {
      for (var detail in detailsList) {
        if (detail is String) {
          try {
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

    if (details.isEmpty) {
      return ListTile(
        leading: const Icon(Icons.info_outline, color: Colors.blue),
        title: Text('$docType: 네트워크 드라이브에서 문서를 찾을 수 없습니다'),
        subtitle: const Text('관리자에게 문의하세요'),
      );
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
              detail['name'] ?? '알 수 없는 파일',
              style: const TextStyle(fontSize: 14),
            ),
            subtitle: Text(
              detail['path'] ?? '경로 없음',
              style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
            ),
            dense: true,
            horizontalTitleGap: 8,
            onTap: () {
              // TODO: 파일 열기 기능 구현
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text('파일 열기: ${detail['path']}'),
                  duration: const Duration(seconds: 2),
                ),
              );
            },
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
          '프로젝트 감사',
          style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, color: Colors.white),
            onPressed: _loadInitialData,
            tooltip: '새로고침',
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
                          '프로젝트 ID: ${_projectData?.projectId ?? 'N/A'}',
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          '부서: ${_projectData?.department ?? 'N/A'}',
                          style: const TextStyle(fontSize: 16),
                        ),
                        Text(
                          '상태: ${_projectData?.status ?? 'N/A'}',
                          style: const TextStyle(fontSize: 16),
                        ),
                        Text(
                          '계약자: ${_projectData?.contractor ?? 'N/A'}',
                          style: const TextStyle(fontSize: 16),
                        ),
                        Text(
                          '타임스탬프: ${_formatDate(DateTime.tryParse(_projectData?.timestamp ?? ''))}',
                          style: const TextStyle(fontSize: 14, color: Colors.grey),
                        ),
                      ],
                    ),
                  ),
                  const Divider(),
                  ExpansionTile(
                    title: const Text(
                      '문서 목록',
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    initiallyExpanded: true,
                    children: [
                      if (_projectData?.documents != null)
                        ..._projectData!.documents.keys.map((String docType) {
                          return ExpansionTile(
                            title: Text(
                              _getDocumentTypeDisplayName(docType),
                              style: const TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                            leading: Icon(
                              _projectData!.documents[docType]!['exists'] == true
                                  ? Icons.check_circle
                                  : Icons.cancel,
                              color: _projectData!.documents[docType]!['exists'] == true
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

  String _getDocumentTypeDisplayName(String docType) {
    switch (docType) {
      case 'contract':
        return '계약서';
      case 'specification':
        return '과업지시서';
      case 'initiation':
        return '착수계';
      case 'agreement':
        return '협약서';
      case 'budget':
        return '예산서';
      case 'deliverable1':
        return '중간보고서';
      case 'deliverable2':
        return '최종보고서';
      case 'completion':
        return '준공계';
      case 'certificate':
        return '인증서';
      case 'evaluation':
        return '평가서';
      default:
        return docType;
    }
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