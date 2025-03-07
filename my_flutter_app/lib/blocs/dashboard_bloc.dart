// /lib/blocs/dashboard_bloc.dart

import 'package:bloc/bloc.dart';
import 'package:equatable/equatable.dart';
import '../models/project_model.dart';
import '../services/api_service.dart';

// Events
abstract class DashboardEvent extends Equatable {
  const DashboardEvent();

  @override
  List<Object> get props => [];
}

class LoadDashboardData extends DashboardEvent {}

// States
abstract class DashboardState extends Equatable {
  const DashboardState();

  @override
  List<Object> get props => [];
}

class DashboardInitial extends DashboardState {}

class DashboardLoading extends DashboardState {}

class DashboardLoaded extends DashboardState {
  final List<ProjectModel> projects;

  const DashboardLoaded({required this.projects});

  @override
  List<Object> get props => [projects];
}

class DashboardError extends DashboardState {
  final String message;

  const DashboardError({required this.message});

  @override
  List<Object> get props => [message];
}

// Bloc
class DashboardBloc extends Bloc<DashboardEvent, DashboardState> {
  final ApiService apiService;

  DashboardBloc({required this.apiService}) : super(DashboardInitial()) {
    on<LoadDashboardData>(_onLoadDashboardData);
  }

  Future<void> _onLoadDashboardData(
    LoadDashboardData event,
    Emitter<DashboardState> emit,
  ) async {
    try {
      emit(DashboardLoading());
      final response = await apiService.fetchProjects();
      emit(DashboardLoaded(projects: response));
    } catch (e) {
      emit(DashboardError(message: e.toString()));
    }
  }
} 