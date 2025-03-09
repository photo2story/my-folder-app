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
        setState(() {
          _selectedProjectId = firstDepartment.children.first.path;
        });
        final chatService = Provider.of<ChatService>(context, listen: false);
        chatService.setProjectId(_selectedProjectId!);
        final apiService = ApiService();
        final projectData = await apiService.fetchProjectAudit(_selectedProjectId!);
        final aiAnalysis = projectData.aiAnalysis ?? 'AI 분석 보고서가 없습니다.';
        print('[DEBUG] Initial aiAnalysis: $aiAnalysis');
        chatService.clearMessages();
        chatService.addMessage(aiAnalysis);
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
            setState(() {
              _selectedProjectId = projectId;
              print('[DEBUG] _selectedProjectId updated to: $_selectedProjectId');
            });
            
            try {
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
              } else {
                print('[WARNING] AI Analysis is null or empty');
              }
              
              if (aiAnalysis == null || aiAnalysis.isEmpty) {
                print('[WARNING] AI Analysis is null or empty');
                chatService.clearMessages();
                chatService.addMessage('이 프로젝트의 AI 분석 보고서가 없습니다.');
              } else {
                chatService.clearMessages();
                chatService.addMessage(aiAnalysis);
                print('[DEBUG] Chat updated with AI analysis');
              }
            } catch (e, stackTrace) {
              print('[ERROR] Error in onProjectTap: $e');
              print('[ERROR] Stack trace: $stackTrace');
              
              final chatService = Provider.of<ChatService>(context, listen: false);
              chatService.clearMessages();
              chatService.addMessage('오류가 발생했습니다: $e');
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