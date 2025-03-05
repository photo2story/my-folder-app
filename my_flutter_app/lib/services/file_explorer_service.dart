// /my_flutter_app/lib/services/file_explorer_service.dart


import 'dart:io';
import 'package:path/path.dart' as path;

class FileNode {
  final String path;
  final String label;
  final bool isDirectory;
  List<FileNode> children;

  FileNode({
    required this.path,
    required this.label,
    required this.isDirectory,
    this.children = const [],
  });
}

class FileExplorerService {
  static const String networkDrivePath = r'D:\github'; // 테스트용 경로

  Future<List<FileNode>> getDirectoryContents(String directoryPath) async {
    try {
      final directory = Directory(directoryPath);
      if (!await directory.exists()) {
        throw Exception('Directory does not exist: $directoryPath');
      }

      List<FileNode> nodes = [];
      await for (var entity in directory.list(followLinks: false)) {
        final basename = path.basename(entity.path);
        nodes.add(
          FileNode(
            path: entity.path,
            label: basename,
            isDirectory: entity is Directory,
          ),
        );
      }

      nodes.sort((a, b) => a.label.compareTo(b.label));
      return nodes;
    } catch (e) {
      print('Error reading directory: $e');
      return [];
    }
  }

  Future<List<FileNode>> loadChildren(String parentPath) async {
    return await getDirectoryContents(parentPath);
  }
}