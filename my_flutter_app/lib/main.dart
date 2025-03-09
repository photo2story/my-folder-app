// /my_flutter_app/lib/main.dart


import 'package:flutter/material.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import 'dart:math' as math;
import 'services/api_service.dart';
import 'services/file_explorer_service.dart';
import 'services/chat_service.dart';
import 'screens/file_explorer_screen.dart';
import 'screens/chat_screen.dart';
import 'package:my_flutter_app/models/file_node.dart' as model;

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Hive.initFlutter();
  await Hive.openBox('chatBox');
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => FileExplorerService(apiService: ApiService())),
        ChangeNotifierProvider(create: (_) => ChatService()),
      ],
      child: const MyApp(),
    ),
  );
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Project Audit Explorer',
      theme: ThemeData(
        primarySwatch: Colors.blue,
        textTheme: const TextTheme(
          bodyMedium: TextStyle(fontFamily: 'NotoSansKR'),
          headlineSmall: TextStyle(fontFamily: 'NotoSansKR'),
          titleMedium: TextStyle(fontFamily: 'NotoSansKR'),
          bodyLarge: TextStyle(fontFamily: 'NotoSansKR'),
          bodySmall: TextStyle(fontFamily: 'NotoSansKR'),
          displayLarge: TextStyle(fontFamily: 'NotoSansKR'),
          displayMedium: TextStyle(fontFamily: 'NotoSansKR'),
          displaySmall: TextStyle(fontFamily: 'NotoSansKR'),
          headlineLarge: TextStyle(fontFamily: 'NotoSansKR'),
          headlineMedium: TextStyle(fontFamily: 'NotoSansKR'),
          titleLarge: TextStyle(fontFamily: 'NotoSansKR'),
          titleSmall: TextStyle(fontFamily: 'NotoSansKR'),
          labelLarge: TextStyle(fontFamily: 'NotoSansKR'),
          labelMedium: TextStyle(fontFamily: 'NotoSansKR'),
          labelSmall: TextStyle(fontFamily: 'NotoSansKR'),
        ),
        fontFamily: 'NotoSansKR',
      ),
      home: const MainScreen(),
    );
  }
}

class MainScreen extends StatefulWidget {
  const MainScreen({Key? key}) : super(key: key);

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  String? _selectedProjectId;
  final _chatController = TextEditingController();
  late FileExplorerService _fileExplorerService;

  @override
  void initState() {
    super.initState();
    _fileExplorerService = Provider.of<FileExplorerService>(context, listen: false);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_selectedProjectId == null) {
      _loadInitialData();
    }
  }

  Future<void> _loadInitialData() async {
    await _fileExplorerService.loadRootDirectory();
    print('[DEBUG] Root directory loaded: ${_fileExplorerService.rootNodes?.length} departments');
    if (_fileExplorerService.rootNodes != null && _fileExplorerService.rootNodes!.isNotEmpty) {
      final firstDepartment = _fileExplorerService.rootNodes!.first;
      await _fileExplorerService.loadChildren(firstDepartment);
      if (firstDepartment.children.isNotEmpty) {
        final firstProjectPath = firstDepartment.children.first.path;
        final parts = firstProjectPath.split('/');
        String projectId = '';
        
        // 경로에서 프로젝트 ID 추출 (예: /10010_플랫폼사업실/A20230001)
        if (parts.length >= 3 && parts[0].isEmpty && parts[1].isNotEmpty && parts[2].isNotEmpty) {
          projectId = parts[2];
        } else {
          // 이름에서 추출 시도 (예: "A20230001 (프로젝트명 - 상태 - 계약자)")
          final nameMatch = RegExp(r'^([A-Z]\d+)').firstMatch(firstDepartment.children.first.name);
          if (nameMatch != null) {
            projectId = nameMatch.group(1)!;
          } else {
            projectId = firstProjectPath; // 다른 방법이 없으면 경로 자체를 사용
          }
        }
        
        print('[DEBUG] Initial project ID extracted: $projectId');
        
        setState(() {
          _selectedProjectId = projectId;
        });
        
        // 모든 문서 노드 자동 확장
        await _fileExplorerService.expandProjectDocuments(projectId);
        print('[DEBUG] All document nodes expanded for initial project: $projectId');
        
        final chatService = Provider.of<ChatService>(context, listen: false);
        chatService.setProjectId(projectId);
        
        final apiService = ApiService();
        final projectData = await apiService.fetchProjectAudit(projectId);
        final aiAnalysis = projectData.aiAnalysis;
        
        if (aiAnalysis != null && aiAnalysis.isNotEmpty) {
          print('[DEBUG] Initial aiAnalysis: ${aiAnalysis.substring(0, math.min(50, aiAnalysis.length))}...');
          
          // 분석 보고서 형식 개선
          final formattedAnalysis = """
# 프로젝트 ${projectData.projectId} 분석 보고서

${aiAnalysis}

---
*프로젝트명: ${projectData.projectName}*
*부서: ${projectData.department}*
*상태: ${projectData.status}*
*계약자: ${projectData.contractor}*
          """;
          
          chatService.clearMessages();
          chatService.addMessage(formattedAnalysis);
        } else {
          print('[WARNING] Initial AI Analysis is null or empty');
          chatService.clearMessages();
          chatService.addMessage('# 이 프로젝트의 AI 분석 보고서가 없습니다.');
        }
        
        print('[DEBUG] Initial project selected: $_selectedProjectId');
      }
    }
  }

  void _openFile(String filePath) async {
    if (filePath.isNotEmpty) {
      final uri = Uri.parse(filePath);
      if (await canLaunchUrl(uri)) {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not open $filePath')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isMobile = MediaQuery.of(context).size.width < 600;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Project Audit Explorer'),
        actions: [
          // 캐시 갱신 버튼
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: '캐시 갱신',
            onPressed: () async {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('캐시를 갱신 중입니다...')),
              );
              await _fileExplorerService.refreshCache();
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('캐시가 갱신되었습니다.')),
              );
            },
          ),
        ],
      ),
      body: isMobile
          ? Column(
              children: [
                Expanded(flex: 6, child: _buildFileExplorer()),
                ChatScreen(selectedProjectId: _selectedProjectId),
              ],
            )
          : Row(
              children: [
                Expanded(flex: 6, child: _buildFileExplorer()),
                ChatScreen(selectedProjectId: _selectedProjectId),
              ],
            ),
    );
  }

  Widget _buildFileExplorer() {
    return Consumer<FileExplorerService>(
      builder: (context, service, child) {
        if (service.isLoading) return const Center(child: Text('로딩 중...'));
        if (service.error != null) return Center(child: Text('Error: ${service.error}'));

        final rootNodes = service.rootNodes ?? [];
        if (rootNodes.isEmpty) return const Center(child: Text('부서가 없습니다'));

        return FileExplorerScreen(
          projectId: _selectedProjectId ?? '',
          onFileTap: _openFile,
          onProjectTap: (projectId) async {
            print('[DEBUG] onProjectTap called with projectId: $projectId');
            print('[DEBUG] Current selected project: $_selectedProjectId');
            
            // 이미 선택된 프로젝트인 경우 중복 처리 방지
            if (_selectedProjectId == projectId) {
              print('[DEBUG] Project already selected, skipping: $projectId');
              return;
            }
            
            setState(() {
              _selectedProjectId = projectId;
              print('[DEBUG] _selectedProjectId updated to: $_selectedProjectId');
            });
            
            try {
              // 모든 문서 노드 자동 확장
              await _fileExplorerService.expandProjectDocuments(projectId);
              print('[DEBUG] All document nodes expanded for project: $projectId');
              
              final chatService = Provider.of<ChatService>(context, listen: false);
              chatService.setProjectId(projectId);
              print('[DEBUG] ChatService projectId set to: ${chatService.currentProjectId}');
              
              final apiService = ApiService();
              print('[DEBUG] Calling fetchProjectAudit for projectId: $projectId');
              final projectData = await apiService.fetchProjectAudit(projectId);
              print('[DEBUG] Project data received: ${projectData.projectId}');
              
              final aiAnalysis = projectData.aiAnalysis;
              if (aiAnalysis != null && aiAnalysis.isNotEmpty) {
                print('[DEBUG] AI Analysis: ${aiAnalysis.substring(0, math.min(50, aiAnalysis.length))}...');
                
                // 채팅 메시지 초기화 및 분석 보고서 추가
                chatService.clearMessages();
                
                // 분석 보고서 형식 개선
                final formattedAnalysis = """
# 프로젝트 ${projectData.projectId} 분석 보고서

${aiAnalysis}

---
*프로젝트명: ${projectData.projectName}*
*부서: ${projectData.department}*
*상태: ${projectData.status}*
*계약자: ${projectData.contractor}*
                """;
                
                chatService.addMessage(formattedAnalysis);
                print('[DEBUG] Chat updated with formatted AI analysis');
              } else {
                print('[WARNING] AI Analysis is null or empty');
                chatService.clearMessages();
                chatService.addMessage('# 이 프로젝트의 AI 분석 보고서가 없습니다.');
              }
            } catch (e, stackTrace) {
              print('[ERROR] Error in onProjectTap: $e');
              print('[ERROR] Stack trace: $stackTrace');
              
              final chatService = Provider.of<ChatService>(context, listen: false);
              chatService.clearMessages();
              chatService.addMessage('# 오류가 발생했습니다\n\n$e');
            }
          },
        );
      },
    );
  }

  @override
  void dispose() {
    _chatController.dispose();
    super.dispose();
  }
}