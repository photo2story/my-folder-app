// /my_flutter_app/lib/main.dart


import 'package:flutter/material.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import 'services/api_service.dart';
import 'services/file_explorer_service.dart';
import 'widgets/tree_view.dart';
import 'package:my_flutter_app/models/file_node.dart' as model;

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Hive.initFlutter();
  await Hive.openBox('chatBox');
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => FileExplorerService(apiService: ApiService())),
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
    print('[DEBUG] Root directory loaded: ${_fileExplorerService.rootNodes?.length} projects');
    if (_fileExplorerService.rootNodes != null && _fileExplorerService.rootNodes!.isNotEmpty) {
      setState(() {
        _selectedProjectId = _fileExplorerService.rootNodes!.first.path;
      });
      final apiService = ApiService();
      final projectData = await apiService.fetchProjectAudit(_selectedProjectId!);
      final aiAnalysis = projectData.aiAnalysis ?? 'AI 분석 보고서가 없습니다.';
      final box = Hive.box('chatBox');
      final messages = List<String>.from(box.get(_selectedProjectId!, defaultValue: <String>[]));
      messages.add(aiAnalysis);
      box.put(_selectedProjectId!, messages);

      await _fileExplorerService.loadChildren(_fileExplorerService.rootNodes!.first);
      print('[DEBUG] Initial children loaded for ${_selectedProjectId}: ${_fileExplorerService.rootNodes!.first.children.length} items');
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
                Expanded(flex: 2, child: _buildProjectList()),
                Expanded(flex: 4, child: _buildFileExplorer()),
                Expanded(flex: 2, child: _buildChatPanel()),
              ],
            )
          : Row(
              children: [
                Expanded(flex: 2, child: _buildProjectList()),
                Expanded(flex: 4, child: _buildFileExplorer()),
                Expanded(flex: 2, child: _buildChatPanel()),
              ],
            ),
    );
  }

  Widget _buildProjectList() {
    return Consumer<FileExplorerService>(
      builder: (context, service, child) {
        if (service.isLoading) return const Center(child: Text('프로젝트 목록 불러오는 중...'));
        if (service.error != null) return Center(child: Text('Error: ${service.error}'));
        final projects = service.rootNodes ?? [];
        if (projects.isEmpty) return const Center(child: Text('프로젝트가 없습니다'));
        return Container(
          color: Colors.grey[200],
          child: ListView.builder(
            itemCount: projects.length,
            itemBuilder: (context, index) {
              final node = projects[index];
              return ListTile(
                selected: node.path == _selectedProjectId,
                title: Text(node.name),
                onTap: () async {
                  setState(() {
                    _selectedProjectId = node.path;
                  });
                  final apiService = ApiService();
                  final projectData = await apiService.fetchProjectAudit(node.path);
                  final aiAnalysis = projectData.aiAnalysis ?? 'AI 분석 보고서가 없습니다.';
                  final box = Hive.box('chatBox');
                  final messages = List<String>.from(box.get(_selectedProjectId!, defaultValue: <String>[]));
                  messages.add(aiAnalysis);
                  box.put(_selectedProjectId!, messages);

                  service.loadChildren(node).then((_) {
                    print('[DEBUG] Children loaded for ${node.path}: ${node.children.length} items');
                  }).catchError((e) {
                    print('[ERROR] Failed to load children: $e');
                  });
                },
              );
            },
          ),
        );
      },
    );
  }

  Widget _buildFileExplorer() {
    return Consumer<FileExplorerService>(
      builder: (context, service, child) {
        if (_selectedProjectId == null) {
          return const Center(child: CircularProgressIndicator()); // 로드 중 표시
        }
        final node = service.rootNodes?.firstWhere(
          (n) => n.path == _selectedProjectId,
          orElse: () => model.FileNode(name: '', path: '', isDirectory: true, children: []),
        );
        if (node == null || service.isLoading) {
          return const Center(child: CircularProgressIndicator());
        }
        if (node.children.isEmpty) {
          return const Center(child: Text('No files available'));
        }
        return TreeView(
          nodes: node.children,
          onNodeTap: (node) {
            if (node.path.isNotEmpty) _openFile(node.path);
          },
          onNodeExpand: (expandedNode) {
            if (!expandedNode.children.isEmpty) return;
            service.loadChildren(expandedNode).then((_) {
              print('[DEBUG] Expanded node ${expandedNode.path} loaded');
            }).catchError((e) {
              print('[ERROR] Failed to expand node: $e');
            });
          },
        );
      },
    );
  }

  Widget _buildChatPanel() {
    return Container(
      color: Colors.grey[100],
      child: Column(
        children: [
          Expanded(
            child: ValueListenableBuilder(
              valueListenable: Hive.box('chatBox').listenable(),
              builder: (context, Box box, _) {
                final messages = box.get(_selectedProjectId ?? '', defaultValue: <String>[]);
                return ListView.builder(
                  itemCount: messages.length,
                  itemBuilder: (context, index) {
                    return ListTile(
                      title: Text(
                        messages[index],
                        style: const TextStyle(fontSize: 14),
                      ),
                      subtitle: Text(
                        DateTime.now().toString().substring(0, 19),
                        style: const TextStyle(fontSize: 10, color: Colors.grey),
                      ),
                    );
                  },
                );
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _chatController,
                    decoration: const InputDecoration(
                      hintText: 'Add a note...',
                      border: OutlineInputBorder(),
                    ),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.send),
                  onPressed: _selectedProjectId == null
                      ? null
                      : () {
                          if (_chatController.text.isNotEmpty) {
                            final box = Hive.box('chatBox');
                            final messages = List<String>.from(box.get(_selectedProjectId!, defaultValue: <String>[]));
                            messages.add(_chatController.text);
                            box.put(_selectedProjectId!, messages);
                            _chatController.clear();
                          }
                        },
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  @override
  void dispose() {
    _chatController.dispose();
    super.dispose();
  }
}